"""
Management command to seed the Badge table from BADGE_DEFINITIONS.

Safe to run multiple times — uses update_or_create on slug.
"""

from django.core.management.base import BaseCommand

from betting.badges import BADGE_DEFINITIONS
from betting.models import Badge


class Command(BaseCommand):
    help = "Seed Badge rows from BADGE_DEFINITIONS in betting/badges.py"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for defn in BADGE_DEFINITIONS:
            _, created = Badge.objects.update_or_create(
                slug=defn["slug"],
                defaults={
                    "name": defn["name"],
                    "description": defn["description"],
                    "icon": defn["icon"],
                    "rarity": defn["rarity"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {defn['slug']}"))
            else:
                updated_count += 1
                self.stdout.write(f"  Updated: {defn['slug']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created_count} created, {updated_count} updated."
            )
        )
