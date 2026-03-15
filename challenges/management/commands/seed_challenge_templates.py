"""
Management command to seed the ChallengeTemplate table.

Safe to run multiple times — uses update_or_create on slug.
"""

from django.core.management.base import BaseCommand

from challenges.challenge_definitions import CHALLENGE_TEMPLATE_DEFINITIONS
from challenges.models import ChallengeTemplate


class Command(BaseCommand):
    help = "Seed ChallengeTemplate rows from challenge_definitions.py"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for defn in CHALLENGE_TEMPLATE_DEFINITIONS:
            _, created = ChallengeTemplate.objects.update_or_create(
                slug=defn["slug"],
                defaults={
                    "title": defn["title"],
                    "description": defn["description"],
                    "icon": defn["icon"],
                    "challenge_type": defn["challenge_type"],
                    "criteria_type": defn["criteria_type"],
                    "criteria_params": defn["criteria_params"],
                    "reward_amount": defn["reward_amount"],
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
