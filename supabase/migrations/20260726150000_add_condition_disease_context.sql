-- Which disease-context reference file (schemas/disease_context.schema.json,
-- fixtures/*.context.json) a condition's interval reasons over. Widening past
-- the single hardcoded "hypothyroidism" demo condition means every condition
-- now names its own context file rather than the app assuming one.
--
-- Not a foreign key: the context files are versioned in the repo, not a
-- Supabase table, so this is a plain slug matched against the filesystem at
-- read time (see backend/loop/disease_context.py).

alter table conditions add column if not exists disease_context_id text;
