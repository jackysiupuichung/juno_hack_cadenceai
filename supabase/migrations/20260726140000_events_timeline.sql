-- Time, as a first-class thing.
--
-- Until now the record held two kinds of time: the date a visit or check-in
-- happened, and the timestamp a row was written. That is enough to say "week 7
-- of this interval" and nothing more. It loses the thing a patient actually
-- tells you — "I stopped taking it after about a fortnight" — because the only
-- date available is the day of the call where they mentioned it. An interval
-- described that way collapses to a list of phone calls.
--
-- The events table is the chronology underneath everything else. Every dated
-- thing writes into it: doses started and stopped, symptoms beginning, tests
-- taken, appointments booked, dose changes. Three properties make it worth a
-- table of its own rather than columns bolted onto the others:
--
--   1. occurred_at and recorded_at are separate. When something happened is
--      not when we heard about it, and conflating them is what makes a
--      timeline read as a call log.
--   2. Precision is explicit. Patients say "a couple of weeks ago". Storing
--      that as a specific timestamp with no qualifier invents a fact the
--      patient never gave, which is the kind of fabrication the brief must
--      never show a doctor. So the estimate travels with how good it is, and
--      with the words it came from.
--   3. Events can be scheduled as well as observed. A blood test due on 12
--      August is the same shape as one taken on 14 August — which is what lets
--      a calendar render both, and lets the brief say a due date passed.

create type event_precision as enum (
  'exact',    -- a timestamp the patient or record actually gave
  'day',      -- "on Tuesday", "the 14th"
  'week',     -- "sometime last week", "about a fortnight ago"
  'month',    -- "back in June"
  'approx'    -- "a while ago" — occurred_at is a rough midpoint, nothing more
);

create type event_source as enum (
  'patient_reported',  -- said on a check-in
  'consultation',      -- said at the visit, extracted from the transcript
  'scheduled',         -- not yet happened; a due date from the plan or guideline
  'derived'            -- computed by Cadence, e.g. an interval boundary
);

create table events (
  id uuid primary key default gen_random_uuid(),
  condition_id uuid not null references conditions (id) on delete cascade,

  -- What kind of thing this is. Deliberately a small closed set: the calendar
  -- and the brief both switch on it, and an open vocabulary would make every
  -- consumer defensive.
  kind text not null check (kind in (
    'visit',            -- a consultation happened
    'medication_start', -- first dose taken
    'medication_stop',  -- stopped taking it
    'dose_change',      -- dose changed — an anchor the monitoring schedule needs
    'test_taken',       -- a blood test actually happened
    'test_result',      -- a result came back
    'symptom_onset',    -- a symptom started
    'symptom_resolved', -- a symptom went away
    'appointment',      -- a future appointment exists
    'check_in',         -- Cadence called
    'other'
  )),

  -- When it happened, as best anyone knows, and how good that estimate is.
  -- Nullable for a scheduled event whose date is not yet fixed.
  occurred_at timestamptz,
  precision event_precision not null default 'day',
  source event_source not null default 'patient_reported',

  -- When Cadence learned of it. Distinct from occurred_at on purpose: a
  -- symptom reported at week 6 that began at week 2 is a four-week gap the
  -- doctor should see, and averaging the two loses it.
  recorded_at timestamptz not null default now(),

  -- Scheduled events only: when this is due, and whether it has been met.
  -- A due date that passes unmet is the brief's most useful observation, so it
  -- must be a row that can be looked up rather than arithmetic re-run on read.
  due_at timestamptz,
  fulfilled_by uuid references events (id) on delete set null,

  -- The patient's own words for the timing. "Just after the bank holiday" is
  -- more honest than any timestamp derived from it, and the brief quotes this
  -- rather than presenting a false-precision date as fact.
  patient_words text not null default '',
  label text not null default '',

  -- Where this came from, so an event can be traced back and so deleting the
  -- parent cleans up after itself.
  visit_id uuid references visits (id) on delete cascade,
  check_in_id uuid references check_ins (id) on delete cascade,
  commitment_id uuid references commitments (id) on delete cascade,

  -- Ids from the disease context this event relates to — a monitoring id for a
  -- scheduled test, a red_flag id for a symptom. Keeps the guideline link
  -- without duplicating the guideline.
  context_ids text[] not null default '{}',

  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- The calendar's query: everything for one condition, in time order.
create index events_condition_occurred_idx on events (condition_id, occurred_at desc nulls last);
-- The "what is coming up / what is overdue" query.
create index events_condition_due_idx on events (condition_id, due_at) where due_at is not null;
create index events_kind_idx on events (condition_id, kind);
create index events_visit_id_idx on events (visit_id);
create index events_check_in_id_idx on events (check_in_id);

-- An event either happened or is due; one with neither is a row nobody can
-- place on a timeline, and silently keeping it would make the chronology lie
-- by omission.
alter table events add constraint events_has_a_time
  check (occurred_at is not null or due_at is not null);

alter table events enable row level security;
