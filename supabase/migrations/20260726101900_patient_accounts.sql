-- Real accounts: a patient can now sign up with email + password instead of
-- being the one hardcoded row every request assumed. Email and password_hash
-- are nullable so the existing hackathon demo patient (still reachable via
-- PATIENT_ID / the seed_demo* management commands) keeps working unchanged
-- until it's explicitly given credentials. Postgres treats multiple NULLs as
-- distinct for a unique constraint, so several credential-less rows can
-- coexist without conflict.
--
-- date_of_birth moves server-side too: it used to live only in the browser's
-- localStorage, which meant signing in on a second device or after clearing
-- storage lost it. Now it travels with the account, like name already does.

alter table patients add column if not exists email text unique;
alter table patients add column if not exists password_hash text;
alter table patients add column if not exists date_of_birth date;
