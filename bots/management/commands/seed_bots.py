"""Management command to create or update bot user accounts and profiles."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from betting.models import UserBalance, UserStats
from bots.models import BotProfile
from bots.personas import BOT_PERSONA_PROMPTS
from bots.registry import BOT_PROFILES
from bots.strategies import (
    AllInAliceStrategy,
    ChaosAgentStrategy,
    DrawSpecialistStrategy,
    FrontrunnerStrategy,
    HomerBotStrategy,
    ParlayStrategy,
    UnderdogStrategy,
    ValueHunterStrategy,
)

User = get_user_model()

# Map strategy classes to BotProfile.StrategyType values
STRATEGY_CLASS_TO_TYPE = {
    FrontrunnerStrategy: BotProfile.StrategyType.FRONTRUNNER,
    UnderdogStrategy: BotProfile.StrategyType.UNDERDOG,
    ParlayStrategy: BotProfile.StrategyType.PARLAY,
    DrawSpecialistStrategy: BotProfile.StrategyType.DRAW_SPECIALIST,
    ValueHunterStrategy: BotProfile.StrategyType.VALUE_HUNTER,
    ChaosAgentStrategy: BotProfile.StrategyType.CHAOS_AGENT,
    AllInAliceStrategy: BotProfile.StrategyType.ALL_IN_ALICE,
    HomerBotStrategy: BotProfile.StrategyType.HOMER,
}


class Command(BaseCommand):
    help = "Create or update bot user accounts and profiles for automated betting"

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
                    "avatar_icon": profile.get("avatar_icon", "robot"),
                    "avatar_bg": profile.get("avatar_bg", "#374151"),
                },
            )

            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created: {profile['display_name']}"))
            else:
                if user.has_usable_password():
                    user.set_unusable_password()
                    user.save(update_fields=["password"])
                updated_count += 1
                self.stdout.write(f"  Updated: {profile['display_name']}")

            # Ensure balance and stats exist
            UserBalance.objects.get_or_create(user=user)
            UserStats.objects.get_or_create(user=user)

            # Create BotProfile if it doesn't exist.
            # On re-seed: sync strategy/cosmetic fields but NEVER overwrite
            # persona_prompt — that's the admin-editable field.
            strategy_type = STRATEGY_CLASS_TO_TYPE.get(
                profile["strategy"], BotProfile.StrategyType.HOMER,
            )
            bp, bp_created = BotProfile.objects.get_or_create(
                user=user,
                defaults={
                    "strategy_type": strategy_type,
                    "team_tla": profile.get("team_tla", ""),
                    "persona_prompt": BOT_PERSONA_PROMPTS.get(profile["email"], ""),
                    "avatar_icon": profile.get("avatar_icon", "robot"),
                    "avatar_bg": profile.get("avatar_bg", "#374151"),
                },
            )
            if not bp_created:
                # Sync non-prompt fields only
                bp.strategy_type = strategy_type
                bp.team_tla = profile.get("team_tla", "")
                bp.avatar_icon = profile.get("avatar_icon", "robot")
                bp.avatar_bg = profile.get("avatar_bg", "#374151")
                bp.save(update_fields=[
                    "strategy_type", "team_tla",
                    "avatar_icon", "avatar_bg", "updated_at",
                ])

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created_count} created, {updated_count} updated."
            )
        )
