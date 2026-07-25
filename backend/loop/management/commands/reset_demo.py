"""Clear the demo patient and everything hanging off them.

The three seed commands each append. None of them clears first, because none of
them can safely assume what else is in the database. Run them a few times while
iterating and the result is what accumulated here: a scratch condition next to
the real one, the same visit inserted twice on the same date, and six briefs
across two conditions where the demo needs one.

That is invisible in the terminal and very visible on the calendar. A condition
list with "Thyroid" and "Thyroid (temporal test)" side by side, or two identical
consultations a scroll apart, reads as a bug in front of a judge — and it is not
one, it is just debris.

So: one command that puts the database back to empty, to be run before seeding.
It deletes the patient row and relies on the ON DELETE CASCADE foreign keys in
supabase/migrations to take conditions, visits, commitments, check-ins,
outcomes, briefs, events, plans, and the medication thread with it. Nothing here
knows the table list, which is the point — a table added later is covered by its
own foreign key rather than by remembering to edit this file.

    manage.py reset_demo [--yes]

It prints what it is about to remove and asks first, because "delete everything
belonging to this patient" is the one operation in this repo that cannot be
undone. --yes skips the prompt for scripted use.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ... import repo


class Command(BaseCommand):
    help = "Delete the demo patient and every row that cascades from them. Asks first."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt.",
        )

    def handle(self, *args, **options):
        patient = repo.get_or_create_patient()

        # Counted before deleting, both so the prompt can say what is at stake
        # and so the summary afterwards is a fact rather than a claim.
        conditions = repo.list_conditions(patient["id"])
        tally = []
        for condition in conditions:
            visits = repo.list_visits(condition["id"])
            briefs = repo.list_briefs(condition["id"])
            tally.append((condition, len(visits), len(briefs)))

        if not conditions:
            self.stdout.write("Nothing to clear — the patient has no conditions.")
            return

        self.stdout.write(f"Patient {patient['id']} ({patient.get('name') or 'unnamed'}):")
        for condition, visits, briefs in tally:
            self.stdout.write(
                f"  {condition['name']} — {visits} visit(s), {briefs} brief(s)"
            )
        self.stdout.write(
            self.style.WARNING(
                "\nThis deletes the patient and everything cascading from them: "
                "conditions, visits, commitments, check-ins, outcomes, briefs, "
                "events, plans, medications, caretaker context. It cannot be undone."
            )
        )

        if not options["yes"]:
            # No stdin (a pipe, a CI run) is an absence of confirmation, not a
            # crash — and it must never read as consent.
            try:
                answer = input("\nType 'delete' to confirm: ").strip().lower()
            except EOFError:
                answer = ""
            if answer != "delete":
                self.stdout.write("Aborted — nothing was deleted. Use --yes to skip the prompt.")
                return

        repo.delete_patient_cascade(patient["id"])

        # get_or_create_patient recreates the row on the next call, so the
        # patient does not stay missing — only their data goes. Recreating it
        # here rather than leaving it to the next command keeps the database in
        # a state the app can serve immediately.
        repo.get_or_create_patient()

        remaining = repo.list_conditions(patient["id"])
        if remaining:
            self.stderr.write(
                self.style.ERROR(
                    f"{len(remaining)} condition(s) survived the delete — the cascade "
                    "did not fire. Check the foreign keys in supabase/migrations."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleared {len(conditions)} condition(s). The patient row is back and empty.\n"
                "Seed the demo with: manage.py seed_demo_interval"
            )
        )
