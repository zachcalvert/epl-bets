"""Convenience command: bots place bets then post pre-match comments.

Simulates real-life users betting on upcoming matches and then going online
to brag about it. Targets the N soonest upcoming matches so comments are
guaranteed to reference live, relevant fixtures.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from betting.models import BetSlip, UserBalance
from bots.models import BotComment
from bots.registry import get_strategy_for_bot
from bots.services import (
    get_best_odds_map,
    get_full_odds_map,
    maybe_topup_bot,
    place_bot_bet,
)
from bots.tasks import generate_bot_comment_task
from matches.models import Match

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Simulate pre-match activity: bots place bets then post pre-match comments "
        "for the N soonest upcoming matches."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--matches",
            type=int,
            default=3,
            help="Number of upcoming matches to target, soonest first (default: 3)",
        )

    def handle(self, *args, **options):
        n = options["matches"]
        now = timezone.now()

        # --- 1. Find the N soonest upcoming matches ---
        upcoming = list(
            Match.objects.filter(
                status__in=[Match.Status.SCHEDULED, Match.Status.TIMED],
                kickoff__gte=now,
            )
            .select_related("home_team", "away_team")
            .order_by("kickoff")[:n]
        )

        if not upcoming:
            self.stdout.write("No upcoming matches found.")
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nTargeting {len(upcoming)} upcoming match(es):"
            )
        )
        for m in upcoming:
            self.stdout.write(f"  {m.home_team} vs {m.away_team}  ({m.kickoff:%a %b %d %H:%M})")

        match_ids = [m.pk for m in upcoming]
        odds_map = get_best_odds_map(match_ids)

        if not odds_map:
            self.stdout.write(self.style.WARNING("No odds found for these matches — aborting."))
            return

        # --- 2. Each bot places bets on the target matches ---
        self.stdout.write(self.style.MIGRATE_HEADING("\nPhase 1 — placing bets:"))

        bots = User.objects.filter(is_bot=True, is_active=True)

        for bot in bots:
            strategy = get_strategy_for_bot(bot)
            if not strategy:
                continue

            maybe_topup_bot(bot)

            try:
                balance = UserBalance.objects.get(user=bot).balance
            except UserBalance.DoesNotExist:
                continue

            # Already-bet match IDs for this bot (within the target set)
            already_bet = set(
                BetSlip.objects.filter(
                    user=bot,
                    match_id__in=match_ids,
                    status=BetSlip.Status.PENDING,
                ).values_list("match_id", flat=True)
            )
            available = [m for m in upcoming if m.pk not in already_bet]
            if not available:
                continue

            # Strategies expect a queryset — build a filtered one
            available_qs = Match.objects.filter(pk__in=[m.pk for m in available]).select_related(
                "home_team", "away_team"
            )

            # ValueHunter needs full per-bookmaker odds
            from bots.strategies import ValueHunterStrategy
            if isinstance(strategy, ValueHunterStrategy):
                odds_map["_full"] = get_full_odds_map(match_ids)

            picks = strategy.pick_bets(available_qs, odds_map, balance)
            bets_placed = 0
            for pick in picks:
                result = place_bot_bet(bot, pick.match_id, pick.selection, pick.stake)
                if result:
                    bets_placed += 1

            if bets_placed:
                self.stdout.write(f"  {bot.display_name}: placed {bets_placed} bet(s)")
            else:
                self.stdout.write(f"  {bot.display_name}: no picks")

        # --- 3. Dispatch pre-match comments (bets now exist) ---
        self.stdout.write(self.style.MIGRATE_HEADING("\nPhase 2 — dispatching pre-match comments:"))

        from bots.comment_service import select_bots_for_match

        total_dispatched = 0
        for match in upcoming:
            bots_for_match = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
            match_dispatched = 0
            for bot in bots_for_match:
                existing_bet = BetSlip.objects.filter(
                    user=bot, match=match, status=BetSlip.Status.PENDING
                ).first()
                bet_slip_id = existing_bet.pk if existing_bet else None
                generate_bot_comment_task.delay(
                    bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH, bet_slip_id
                )
                match_dispatched += 1

            label = f"{match.home_team} vs {match.away_team}"
            self.stdout.write(f"  {label}: dispatched {match_dispatched} comment task(s)")
            total_dispatched += match_dispatched

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {total_dispatched} pre-match comment task(s) queued."
            )
        )
