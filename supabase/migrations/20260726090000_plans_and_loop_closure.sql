-- The caretaker's plan, and the plumbing that closes the loop back to the
-- next consultation. Three changes, each fixing something the first cut left
-- open:
--
--   1. plans — the interval agenda, decided once when the visit is summarised
--      rather than improvised call by call. Persisting it is what lets the
--      brief report what was planned against what was actually asked; an item
--      no call ever reached is a finding, not a silent gap.
--   2. A status vocabulary that matches across tables. outcomes allowed
--      'partial' and commitments did not, so a partial outcome silently never
--      updated its commitment and the thing sat at 'pending' forever.
--   3. visits.previous_brief_id — the return arrow. A visit that was walked
--      into with a brief records which one, so the interval it opens knows
--      what the interval before it established.

-- Every statement below is idempotent. This migration is often applied by
-- hand in the SQL editor rather than by `supabase db push`, and a half-applied
-- run must be safe to simply re-run.

create table if not exists plans (
  id uuid primary key default gen_random_uuid(),
  visit_id uuid not null references visits (id) on delete cascade,
  -- The check_in_plan.schema.json body: interval_goal, items, call_schedule.
  content jsonb not null,
  -- Which disease context the plan was reasoned over. Kept so a plan stays
  -- interpretable if the curated file is later revised.
  condition_context text not null default '',
  created_at timestamptz not null default now()
);
create index if not exists plans_visit_id_idx on plans (visit_id);

-- One plan per visit: the agenda belongs to the interval, and an interval is
-- opened by exactly one consultation. Re-planning replaces rather than
-- accumulates.
create unique index if not exists plans_visit_id_unique on plans (visit_id);

-- Which planned items a call actually reached. Written from the agent's
-- `covers`, so the brief can distinguish "asked and answered" from "never
-- asked" without re-reading every transcript.
alter table check_ins add column if not exists covered_item_ids text[] not null default '{}';

-- 'partial' is a real answer — the patient started the course and stopped, took
-- four of seven doses. It belongs in the same vocabulary as the outcome that
-- produced it, and interval.py already treats it as still-open.
--
-- The original constraint was declared inline and so carries whatever name
-- Postgres generated. That is conventionally commitments_status_check, but the
-- name is dropped by lookup rather than by assumption: guessing wrong here
-- fails the whole migration.
do $$
declare
  constraint_name text;
begin
  select con.conname into constraint_name
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  where rel.relname = 'commitments'
    and con.contype = 'c'
    and pg_get_constraintdef(con.oid) like '%status%';

  if constraint_name is not null then
    execute format('alter table commitments drop constraint %I', constraint_name);
  end if;
end $$;

alter table commitments
  add constraint commitments_status_check
  check (status in ('pending', 'done', 'not_done', 'partial', 'changed'));

-- The return arrow. Null for a first visit, and for any visit the patient
-- walked into cold — which is the state Cadence exists to end, so it is worth
-- being able to count.
alter table visits add column if not exists previous_brief_id uuid references briefs (id) on delete set null;
create index if not exists visits_previous_brief_id_idx on visits (previous_brief_id);

alter table plans enable row level security;
