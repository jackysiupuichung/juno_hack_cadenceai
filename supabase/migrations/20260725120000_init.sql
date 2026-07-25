-- Cadence / LOOP data model — see product_doc.md "Data model" section.
-- One hardcoded patient for the hackathon MVP; no auth. RLS is enabled with
-- no anon/authenticated policies, so only the service-role key (used by the
-- Django backend) can read or write — the frontend never talks to Supabase
-- directly.

create extension if not exists pgcrypto;
create extension if not exists vector;

create table patients (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table conditions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients (id) on delete cascade,
  name text not null,
  status text not null default 'active' check (status in ('active', 'resolved')),
  created_at timestamptz not null default now()
);
create index conditions_patient_id_idx on conditions (patient_id);

create table visits (
  id uuid primary key default gen_random_uuid(),
  condition_id uuid not null references conditions (id) on delete cascade,
  date date not null,
  care_setting text not null check (care_setting in ('gp', 'hospital', 'emergency', 'specialist')),
  clinician_name text not null default '',
  organisation text not null default '',
  transcript text not null default '',
  summary jsonb,
  -- Unused by this build; present to show the longitudinal record this
  -- becomes (semantic search across visits).
  embedding vector(1536),
  created_at timestamptz not null default now()
);
create index visits_condition_id_idx on visits (condition_id);

create table commitments (
  id uuid primary key default gen_random_uuid(),
  visit_id uuid not null references visits (id) on delete cascade,
  text text not null,
  type text not null check (type in ('medication', 'test', 'watch_for', 'followup', 'lifestyle')),
  timeframe text not null default '',
  source_quote text not null default '',
  status text not null default 'pending' check (status in ('pending', 'done', 'not_done', 'changed')),
  created_at timestamptz not null default now()
);
create index commitments_visit_id_idx on commitments (visit_id);
create index commitments_status_idx on commitments (status);

create table check_ins (
  id uuid primary key default gen_random_uuid(),
  condition_id uuid not null references conditions (id) on delete cascade,
  date date not null,
  transcript text not null default '',
  raw jsonb,
  created_at timestamptz not null default now()
);
create index check_ins_condition_id_idx on check_ins (condition_id);

create table outcomes (
  id uuid primary key default gen_random_uuid(),
  check_in_id uuid not null references check_ins (id) on delete cascade,
  commitment_id uuid not null references commitments (id) on delete cascade,
  status text not null default 'unknown' check (status in ('done', 'not_done', 'partial', 'changed', 'unknown')),
  patient_words text not null default '',
  note text not null default ''
);
create index outcomes_check_in_id_idx on outcomes (check_in_id);
create index outcomes_commitment_id_idx on outcomes (commitment_id);

create table briefs (
  id uuid primary key default gen_random_uuid(),
  condition_id uuid not null references conditions (id) on delete cascade,
  generated_at timestamptz not null default now(),
  content jsonb not null
);
create index briefs_condition_id_idx on briefs (condition_id);

alter table patients enable row level security;
alter table conditions enable row level security;
alter table visits enable row level security;
alter table commitments enable row level security;
alter table check_ins enable row level security;
alter table outcomes enable row level security;
alter table briefs enable row level security;
