"""
Seed the drugs reference table (schemas/drug.schema.json) with a handful of
common medications, NHS-sourced, so /api/checkin and /api/brief have
something real to match a visit's medications against.

Requires only SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY (and the migrations in
supabase/migrations/ already applied).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ... import repo

DRUGS = [
    {
        "drug": {
            "id": "levothyroxine",
            "name": "Levothyroxine",
            "plain_name": "thyroid hormone replacement",
            "typical_use": "Underactive thyroid (hypothyroidism).",
            "aliases": [
                "synthetic thyroid",
                "thyroid replacement medication",
                "thyroxine",
                "levothyroxine sodium",
            ],
        },
        "sources": [
            {
                "id": "nhs_levothyroxine",
                "title": "Levothyroxine",
                "url": "https://www.nhs.uk/medicines/levothyroxine/",
                "publisher": "NHS",
                "retrieved": "2026-07-25",
            }
        ],
        "interactions": [
            "Calcium and iron supplements can reduce absorption if taken too close together.",
        ],
        "side_effects": [
            "Racing heart or palpitations",
            "Shaky hands or tremor",
            "Feeling hot or sweating more than usual",
            "Headache",
            "Diarrhoea",
        ],
        "monitoring_note": "Dose is usually adjusted by blood test (TSH) every few weeks until it settles.",
        "safety": {
            "framing_rule": "Surface these only as recognition of a symptom the patient already described — never as a suggestion to change the dose."
        },
    },
    {
        "drug": {
            "id": "metformin",
            "name": "Metformin",
            "plain_name": "diabetes tablets",
            "typical_use": "Type 2 diabetes.",
            "aliases": ["Glucophage", "diabetes tablets", "sugar tablets"],
        },
        "sources": [
            {
                "id": "nhs_metformin",
                "title": "Metformin",
                "url": "https://www.nhs.uk/medicines/metformin/",
                "publisher": "NHS",
                "retrieved": "2026-07-25",
            }
        ],
        "interactions": [
            "Alcohol in excess increases the risk of a rare but serious side effect (lactic acidosis).",
        ],
        "side_effects": [
            "Diarrhoea or stomach upset, especially when starting",
            "Nausea",
            "Metallic taste",
            "Loss of appetite",
        ],
        "monitoring_note": "Kidney function is usually checked periodically while taking this.",
        "safety": {
            "framing_rule": "Surface these only as recognition of a symptom the patient already described — never as a suggestion to change the dose."
        },
    },
    {
        "drug": {
            "id": "sertraline",
            "name": "Sertraline",
            "plain_name": "antidepressant",
            "typical_use": "Depression and anxiety.",
            "aliases": ["Zoloft", "Lustral", "antidepressant tablets"],
        },
        "sources": [
            {
                "id": "nhs_sertraline",
                "title": "Sertraline",
                "url": "https://www.nhs.uk/medicines/sertraline/",
                "publisher": "NHS",
                "retrieved": "2026-07-25",
            }
        ],
        "interactions": [
            "Should not be combined with other medicines that raise serotonin without medical advice.",
        ],
        "side_effects": [
            "Nausea, especially in the first couple of weeks",
            "Trouble sleeping",
            "Feeling more anxious at first",
            "Dry mouth",
        ],
        "monitoring_note": "Effects on mood are usually reviewed a few weeks after starting or changing dose.",
        "safety": {
            "framing_rule": "Surface these only as recognition of a symptom the patient already described — never as a suggestion to change the dose."
        },
    },
]


class Command(BaseCommand):
    help = "Seed a handful of common drugs into the drugs reference table."

    def handle(self, *args, **options):
        created = 0
        for content in DRUGS:
            slug = content["drug"]["id"]
            if repo.get_drug(slug):
                self.stdout.write(f"   {slug} already exists, skipping")
                continue
            repo.create_drug(content)
            created += 1
            self.stdout.write(self.style.SUCCESS(f"   seeded {slug}"))
        self.stdout.write(self.style.SUCCESS(f"\nDone. {created} drug(s) seeded."))
