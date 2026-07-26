-- Login moves from email to a unique username — the existing "name" column
-- doubles as the login handle instead of adding a separate column, so an
-- account is just name + date_of_birth + password_hash. email/password_hash
-- stay as columns (harmless, unused going forward) rather than being dropped:
-- dropping a column that already holds real signed-up accounts' data is
-- one-way, and isn't needed for this change to work.

alter table patients add constraint patients_name_unique unique (name);
