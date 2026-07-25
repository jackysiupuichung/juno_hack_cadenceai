-- LOOP — initial schema
-- Patient-side loop-closing scribe. Everything patient-owned. RLS from the start.
-- See SPEC.md for design notes.

create extension if not exists vector;
create extension if not exists "uuid-ossp";

-- ─────────────────────────────────────────────
create table patients (
  id         uuid primary key default gen_random_uuid(),
  label      text,
  conditions text[],                       -- chronic wedge, e.g. ['POTS','ME/CFS']
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────────
-- a visit anchors an interval
create table visits (
  id         uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  visited_at timestamptz not null,
  clinician  text,                          -- 'Dr Okafor, cardiology'
  transcript text,                          -- from ElevenLabs Scribe
  summary    text,                          -- Claude plain-language summary
  created_at timestamptz default now()
);

-- ─────────────────────────────────────────────
-- a commitment is something agreed IN a visit to be checked AFTER it
create type commitment_kind as enum ('trial','test','watch','referral','medication','lifestyle');
create type commitment_status as enum ('open','done','not_done','partial','superseded');

create table commitments (
  id            uuid primary key default gen_random_uuid(),
  visit_id      uuid not null references visits(id) on delete cascade,
  patient_id    uuid not null references patients(id) on delete cascade,
  kind          commitment_kind not null,
  description   text not null,              -- "Try midodrine 2.5mg for 6 weeks, then reassess"
  review_after  interval,                   -- '6 weeks'
  review_by     timestamptz,                -- visited_at + review_after (set in app)
  discriminator text,                       -- what tells us it worked / didn't
  status        commitment_status default 'open',
  created_at    timestamptz default now()
);

-- ─────────────────────────────────────────────
-- a checkin is a follow-through data point against a commitment
create table checkins (
  id            uuid primary key default gen_random_uuid(),
  commitment_id uuid not null references commitments(id) on delete cascade,
  patient_id    uuid not null references patients(id) on delete cascade,
  checked_at    timestamptz not null,
  channel       text default 'voice',
  content       text not null,              -- what the patient reported
  signal        jsonb,                      -- optional: {"symptom":"dizziness","change":"worse","pattern":"postprandial"}
  created_at    timestamptz default now()
);

create index commitments_patient on commitments (patient_id, review_by);
create index checkins_commitment on checkins (commitment_id, checked_at);

-- ─────────────────────────────────────────────
-- RLS. Demo: service_role only. Real deployment: scope to auth.uid().
alter table patients    enable row level security;
alter table visits      enable row level security;
alter table commitments enable row level security;
alter table checkins    enable row level security;

create policy "service_all_patients"    on patients    for all using (auth.role() = 'service_role');
create policy "service_all_visits"      on visits      for all using (auth.role() = 'service_role');
create policy "service_all_commitments" on commitments for all using (auth.role() = 'service_role');
create policy "service_all_checkins"    on checkins    for all using (auth.role() = 'service_role');
