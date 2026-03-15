import logging

from django.db import transaction

from betting.models import UserStats

logger = logging.getLogger(__name__)


def record_bet_result(user, *, won, stake, payout):
    """
    Update UserStats after a single bet or parlay settles.

    Args:
        user: The user whose stats to update.
        won: True if the bet won, False if it lost.
        stake: The bet stake amount.
        payout: The payout amount (0 for losses).
    """
    with transaction.atomic():
        stats, _ = UserStats.objects.select_for_update().get_or_create(user=user)

        stats.total_bets += 1
        stats.total_staked += stake
        stats.total_payout += payout

        if won:
            stats.total_wins += 1
            stats.current_streak = max(stats.current_streak, 0) + 1
            stats.best_streak = max(stats.best_streak, stats.current_streak)
        else:
            stats.total_losses += 1
            stats.current_streak = min(stats.current_streak, 0) - 1

        stats.net_profit = stats.total_payout - stats.total_staked

        stats.save(
            update_fields=[
                "total_bets",
                "total_wins",
                "total_losses",
                "total_staked",
                "total_payout",
                "net_profit",
                "current_streak",
                "best_streak",
            ]
        )

    logger.info(
        "record_bet_result: user=%s won=%s streak=%d best=%d profit=%s",
        user.pk,
        won,
        stats.current_streak,
        stats.best_streak,
        stats.net_profit,
    )
