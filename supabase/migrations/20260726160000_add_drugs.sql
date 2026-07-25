-- Generic medication reference (schemas/drug.schema.json), matched against a
-- visit's medications by name/alias. Unlike disease_context, drugs are looked
-- up by name across many visits' medications rather than opted into once by
-- id, so they live in Supabase rather than being read straight off disk.

create table if not exists drugs (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  content jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists drugs_slug_idx on drugs (slug);

alter table drugs enable row level security;
