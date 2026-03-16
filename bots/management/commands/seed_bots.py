"""Management command to create or update bot user accounts."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from betting.models import UserBalance, UserStats
from bots.registry import BOT_PROFILES

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update bot user accounts for automated betting"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for profile in BOT_PROFILES:
            user, created = User.objects.update_or_create(
                email=profile["email"],
                defaults={
                    "display_name": profile["display_name"],
                    "is_bot": True,
                    "is_active": True,
                },
            )

            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {profile['display_name']}"))
            else:
                updated_count += 1
                self.stdout.write(f"  Updated: {profile['display_name']}")

            # Ensure balance and stats exist
            UserBalance.objects.get_or_create(user=user)
            UserStats.objects.get_or_create(user=user)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created_count} created, {updated_count} updated."
            )
        )
