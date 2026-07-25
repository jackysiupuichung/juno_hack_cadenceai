-- Consultations become standalone: a visit can exist without a condition,
-- tagged to one now or linked later. Visits therefore need their own
-- patient_id (previously reached only via condition_id). Deleting a
-- condition unlinks its visits instead of deleting them.
--
-- Every statement below is idempotent, matching this repo's convention for
-- migrations applied by hand in the SQL editor.

alter table visits add column if not exists patient_id uuid references patients (id) on delete cascade;
update visits v set patient_id = c.patient_id from conditions c where c.id = v.condition_id and v.patient_id is null;
alter table visits alter column patient_id set not null;
create index if not exists visits_patient_id_idx on visits (patient_id);

alter table visits alter column condition_id drop not null;

-- The inline FK on condition_id was declared without a name, so Postgres
-- generated one — conventionally visits_condition_id_fkey, but the name is
-- looked up rather than assumed: guessing wrong here fails the whole
-- migration (see 20260726090000's commitments_status_check for the same
-- pattern).
do $$
declare
  constraint_name text;
begin
  select con.conname into constraint_name
  from pg_constraint con
  join pg_class rel on rel.oid = con.conrelid
  where rel.relname = 'visits'
    and con.contype = 'f'
    -- pg_get_constraintdef renders keywords (FOREIGN KEY, REFERENCES) in
    -- uppercase but preserves identifier case, so match on the identifiers
    -- only — a case-sensitive LIKE against the keywords would never hit.
    and pg_get_constraintdef(con.oid) like '%condition_id%conditions%';

  if constraint_name is not null then
    execute format('alter table visits drop constraint %I', constraint_name);
    execute format(
      'alter table visits add constraint %I foreign key (condition_id) references conditions (id) on delete set null',
      constraint_name
    );
  end if;
end $$;
