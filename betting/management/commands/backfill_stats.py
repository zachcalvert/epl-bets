from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

from betting.models import BetSlip, Parlay, UserStats

User = get_user_model()


class Command(BaseCommand):
    help = "Backfill UserStats from existing BetSlip and Parlay history"

    def handle(self, *args, **options):
        users = User.objects.filter(
            Q(bets__isnull=False) | Q(parlays__isnull=False)
        ).distinct()

        created_count = 0
        updated_count = 0

        for user in users:
            # Aggregate single bets (settled only)
            settled_bets = BetSlip.objects.filter(
                user=user, status__in=[BetSlip.Status.WON, BetSlip.Status.LOST]
            )
            bet_agg = settled_bets.aggregate(
                total_staked=Sum("stake"),
                total_payout=Sum("payout"),
            )
            bet_wins = settled_bets.filter(status=BetSlip.Status.WON).count()
            bet_losses = settled_bets.filter(status=BetSlip.Status.LOST).count()

            # Aggregate parlays (settled only)
            settled_parlays = Parlay.objects.filter(
                user=user, status__in=[Parlay.Status.WON, Parlay.Status.LOST]
            )
            parlay_agg = settled_parlays.aggregate(
                total_staked=Sum("stake"),
                total_payout=Sum("payout"),
            )
            parlay_wins = settled_parlays.filter(status=Parlay.Status.WON).count()
            parlay_losses = settled_parlays.filter(status=Parlay.Status.LOST).count()

            total_bets = bet_wins + bet_losses + parlay_wins + parlay_losses
            total_wins = bet_wins + parlay_wins
            total_losses = bet_losses + parlay_losses
            total_staked = (bet_agg["total_staked"] or Decimal("0")) + (
                parlay_agg["total_staked"] or Decimal("0")
            )
            total_payout = (bet_agg["total_payout"] or Decimal("0")) + (
                parlay_agg["total_payout"] or Decimal("0")
            )
            net_profit = total_payout - total_staked

            # Compute streaks by replaying settled bets/parlays chronologically
            current_streak, best_streak = self._compute_streaks(user)

            stats, created = UserStats.objects.update_or_create(
                user=user,
                defaults={
                    "total_bets": total_bets,
                    "total_wins": total_wins,
                    "total_losses": total_losses,
                    "total_staked": total_staked,
                    "total_payout": total_payout,
                    "net_profit": net_profit,
                    "current_streak": current_streak,
                    "best_streak": best_streak,
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {created_count} created, {updated_count} updated"
            )
        )

    def _compute_streaks(self, user):
        """Replay bet history chronologically to compute current and best win streaks."""
        # Merge settled singles and parlays into a single timeline sorted by timestamp
        timeline = []

        for bet in BetSlip.objects.filter(
            user=user, status__in=[BetSlip.Status.WON, BetSlip.Status.LOST]
        ).order_by("updated_at"):
            timeline.append((bet.updated_at, bet.status == BetSlip.Status.WON))

        for parlay in Parlay.objects.filter(
            user=user, status__in=[Parlay.Status.WON, Parlay.Status.LOST]
        ).order_by("updated_at"):
            timeline.append((parlay.updated_at, parlay.status == Parlay.Status.WON))

        # Sort by timestamp so singles and parlays are properly interleaved
        timeline.sort(key=lambda x: x[0])

        current_streak = 0
        best_streak = 0

        for _, won in timeline:
            if won:
                current_streak = max(current_streak, 0) + 1
                best_streak = max(best_streak, current_streak)
            else:
                current_streak = min(current_streak, 0) - 1

        return current_streak, best_streak
