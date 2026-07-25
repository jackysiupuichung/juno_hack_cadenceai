-- The "New appointment" screen asks for a clinic/organisation address
-- alongside its name, so the visit record can show it in full.
alter table visits add column organisation_address text not null default '';
