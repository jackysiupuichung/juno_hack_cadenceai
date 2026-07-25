-- The medication thread, persisted — and the caretaker's standing context.
--
-- capture/medication.py already models the prescription thread properly: a
-- value carries its provenance, a label fills gaps without overwriting the
-- clinician, and nothing reaches a reminder until the patient has confirmed it.
-- None of that survived a process restart. `from_summary` rebuilt the thread
-- from the visit summary on every call, which means every fact the patient gave
-- on a call — collected it on Tuesday, takes it at 7:30, missed two doses — was
-- computed, used once, and dropped. The thread reset to "nothing established"
-- each time, so week 6 asked the same opening questions as day 1.
--
-- That is the bug this migration fixes. Two tables:
--
--   1. medications — one row per prescribed medicine, holding both the clinical
--      fields (with provenance) and the thread state that accumulates across
--      calls. This is the state `from_summary` seeds and check-ins update.
--   2. caretaker_context — the standing facts about the person that no visit
--      summary contains and every call needs: what to call them, when it is
--      reasonable to ring, what makes taking a tablet hard for them.
--
-- Idempotent throughout, for the same reason as the plans migration: this is
-- often applied by hand in the SQL editor and a half-applied run must re-run
-- safely.

-- ---------------------------------------------------------------------------
-- Provenance and thread-state vocabularies.
--
-- These mirror the enums in capture/medication.py one-for-one, deliberately.
-- A value whose source is storable but not checkable would let a LABEL value be
-- written where the code believes only CLINICIAN can appear, and the whole
-- point of the type there is that provenance is never inferred later.
-- ---------------------------------------------------------------------------

do $$ begin
  create type medication_source as enum ('clinician', 'label', 'general');
exception when duplicate_object then null; end $$;

do $$ begin
  create type medication_confirmation as enum ('confirmed', 'pending', 'rejected');
exception when duplicate_object then null; end $$;

do $$ begin
  create type medication_collection as enum (
    'unknown', 'not_collected', 'collected', 'not_applicable'
  );
exception when duplicate_object then null; end $$;

do $$ begin
  create type medication_adherence as enum (
    'unknown', 'every_day', 'missed_once', 'missed_more', 'stopped'
  );
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- medications
--
-- Hung off the visit that prescribed it, not the condition. A prescription is
-- something a specific consultation did, and the brief needs to say which one —
-- "started at the June appointment, still not collected" is the finding. The
-- condition is reachable through the visit, so storing it again would be a
-- second copy that can disagree with the first.
--
-- The five clinical fields are each stored as three columns rather than one
-- jsonb blob: text, source, confirmation. It is more columns, and it is worth
-- it — a filter for "anything still pending the patient's confirmation" is the
-- query that stops a misread label reaching a reminder, and it should be an
-- index, not a jsonb scan over every row.
-- ---------------------------------------------------------------------------

create table if not exists medications (
  id uuid primary key default gen_random_uuid(),
  visit_id uuid not null references visits (id) on delete cascade,

  -- The clinical fields. Empty text is a gap, and a gap is a legitimate state:
  -- a consultation that said "a very low dose" genuinely did not state a
  -- dosage, and medication.py reports that rather than completing it. There is
  -- no not-null constraint here for exactly that reason.
  name text not null default '',
  name_source medication_source not null default 'clinician',
  name_confirmation medication_confirmation not null default 'confirmed',

  dosage text not null default '',
  dosage_source medication_source not null default 'clinician',
  dosage_confirmation medication_confirmation not null default 'confirmed',

  frequency text not null default '',
  frequency_source medication_source not null default 'clinician',
  frequency_confirmation medication_confirmation not null default 'confirmed',

  duration text not null default '',
  duration_source medication_source not null default 'clinician',
  duration_confirmation medication_confirmation not null default 'confirmed',

  instructions text not null default '',
  instructions_source medication_source not null default 'clinician',
  instructions_confirmation medication_confirmation not null default 'confirmed',

  -- Thread state. Unlike the fields above these have no provenance question:
  -- they come from the patient on a call, directly. This is the part that was
  -- being recomputed and lost.
  collection medication_collection not null default 'unknown',

  -- Tri-state on purpose, and the reason this is a nullable boolean rather than
  -- two: "has not taken the first dose" and "we have never asked" are different
  -- facts, and only the first is worth reporting to a doctor. Collapsing them
  -- to false would put a finding in the brief that no patient ever said.
  first_dose_taken boolean,

  reminder_time text not null default '',   -- "07:30", as the patient chose it
  adherence medication_adherence not null default 'unknown',
  label_seen boolean not null default false,

  -- Day of the interval this was last chased on, so COLLECTION_CHASE_DAYS can
  -- be honoured across calls instead of re-chasing from zero every time.
  last_chased_day integer,

  -- Discrepancy notes — "the label says 50mcg, your clinician said 25mcg".
  -- Free text because they are written to be read aloud, and quoted verbatim
  -- into the brief rather than parsed.
  notes text[] not null default '{}',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists medications_visit_id_idx on medications (visit_id);

-- The two queries that actually run: what still needs the patient's agreement
-- before a reminder can use it, and what has a reminder to fire.
create index if not exists medications_pending_idx on medications (visit_id)
  where name_confirmation = 'pending'
     or dosage_confirmation = 'pending'
     or frequency_confirmation = 'pending'
     or duration_confirmation = 'pending';

create index if not exists medications_reminder_idx on medications (reminder_time)
  where reminder_time <> '';

-- A rejected value must not keep its text. medication.confirm_label clears it
-- deliberately — a value the patient said is wrong is worse than no value,
-- because it looks filled and nothing downstream thinks to ask again. Enforced
-- here so a direct write cannot reintroduce the state the code is careful to
-- avoid.
do $$ begin
  alter table medications add constraint medications_rejected_is_empty check (
    (name_confirmation <> 'rejected' or name = '')
    and (dosage_confirmation <> 'rejected' or dosage = '')
    and (frequency_confirmation <> 'rejected' or frequency = '')
    and (duration_confirmation <> 'rejected' or duration = '')
    and (instructions_confirmation <> 'rejected' or instructions = '')
  );
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- caretaker_context
--
-- What the caretaker knows about the person before it says a word.
--
-- Everything the check-in agent currently has is clinical: the interval facts,
-- the disease context, the plan. That is enough to know what to ask and nothing
-- about how to ask it. The result is a call that is correct and stilted — it
-- rings at 9am when the patient works nights, uses a name they do not go by,
-- and asks about a tablet without knowing they cannot swallow tablets.
--
-- None of this belongs in the disease context, which is a curated clinical
-- reference shared across every patient with that condition. It belongs to the
-- person and follows them across conditions, which is why it hangs off the
-- patient rather than the condition.
--
-- The boundary this table respects: it holds facts about circumstances, never
-- clinical judgements. "Cannot swallow tablets" is a circumstance. "Should be
-- switched to a liquid formulation" is a treatment change, which is the CDS
-- line, and it must not appear here.
-- ---------------------------------------------------------------------------

create table if not exists caretaker_context (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients (id) on delete cascade,

  -- How to address them. Distinct from patients.name, which is the name on the
  -- record; this is the one they answer to.
  preferred_name text not null default '',

  -- When it is reasonable to ring, in the patient's own words — "mornings are
  -- bad, after 2pm is fine". Free text rather than a time range because the
  -- real constraint is rarely a clean interval, and a lossy encoding of it is
  -- worse than the sentence.
  contact_window text not null default '',

  -- The wedge population tires easily; a call that is fine for one person is
  -- exhausting for another. Governs how many agenda items survive onto a single
  -- call.
  call_length_preference text not null default 'standard'
    check (call_length_preference in ('brief', 'standard', 'unhurried')),

  -- Practical circumstances that change how the plan actually happens: cannot
  -- swallow tablets, no transport to the clinic, works nights, someone else
  -- manages the pillbox. Facts, never recommendations.
  living_situation text not null default '',
  access_needs text[] not null default '{}',
  medication_barriers text[] not null default '{}',

  -- What matters to them about their own care, in their words. This is the
  -- thread that eventually makes the longitudinal record readable for "what
  -- matters", per the vision — stored now because it is only capturable in the
  -- moment the patient says it.
  priorities text[] not null default '{}',

  -- Who else is involved, and whether they may be told anything. Consent is
  -- explicit and defaults to false: a named contact is not permission to speak
  -- to them, and assuming otherwise discloses health information the patient
  -- never agreed to share.
  supporter_name text not null default '',
  supporter_relationship text not null default '',
  supporter_may_be_contacted boolean not null default false,

  -- Anything else the caretaker should know that has no column. Deliberately
  -- last and deliberately free: the alternative is inventing a column per
  -- patient, and this is one demo patient.
  notes text not null default '',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- One context per patient. It is the standing description of a person, and two
-- of them would mean two answers to "what should the caretaker call you".
create unique index if not exists caretaker_context_patient_id_unique
  on caretaker_context (patient_id);

-- A named supporter is required before contacting one is possible. Consent
-- without a person to contact is a flag with nothing behind it, and the failure
-- mode — a true flag surviving the deletion of the name — is the one that leads
-- to disclosing to an unspecified third party.
do $$ begin
  alter table caretaker_context add constraint caretaker_context_supporter_named check (
    not supporter_may_be_contacted or length(trim(supporter_name)) > 0
  );
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- updated_at, maintained by the database.
--
-- Both tables are written field-by-field as calls land, and "when did this last
-- change" is the ordering signal for anything that reconciles them. Left to the
-- application it would be set on most writes and forgotten on the ones added
-- later, which is the version that quietly goes stale.
-- ---------------------------------------------------------------------------

create or replace function touch_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end $$ language plpgsql;

drop trigger if exists medications_touch_updated_at on medications;
create trigger medications_touch_updated_at
  before update on medications
  for each row execute function touch_updated_at();

drop trigger if exists caretaker_context_touch_updated_at on caretaker_context;
create trigger caretaker_context_touch_updated_at
  before update on caretaker_context
  for each row execute function touch_updated_at();

alter table medications enable row level security;
alter table caretaker_context enable row level security;
