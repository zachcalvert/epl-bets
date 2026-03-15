from decimal import Decimal

import pytest

from betting.models import UserStats
from betting.stats import record_bet_result
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestRecordBetResult:
    def test_creates_stats_on_first_win(self):
        user = UserFactory()

        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("21.00"))

        stats = UserStats.objects.get(user=user)
        assert stats.total_bets == 1
        assert stats.total_wins == 1
        assert stats.total_losses == 0
        assert stats.total_staked == Decimal("10.00")
        assert stats.total_payout == Decimal("21.00")
        assert stats.net_profit == Decimal("11.00")
        assert stats.current_streak == 1
        assert stats.best_streak == 1

    def test_creates_stats_on_first_loss(self):
        user = UserFactory()

        record_bet_result(user, won=False, stake=Decimal("10.00"), payout=Decimal("0"))

        stats = UserStats.objects.get(user=user)
        assert stats.total_bets == 1
        assert stats.total_wins == 0
        assert stats.total_losses == 1
        assert stats.net_profit == Decimal("-10.00")
        assert stats.current_streak == -1
        assert stats.best_streak == 0

    def test_win_streak_increments(self):
        user = UserFactory()

        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))
        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))
        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))

        stats = UserStats.objects.get(user=user)
        assert stats.current_streak == 3
        assert stats.best_streak == 3

    def test_loss_breaks_win_streak(self):
        user = UserFactory()

        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))
        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))
        record_bet_result(user, won=False, stake=Decimal("10.00"), payout=Decimal("0"))

        stats = UserStats.objects.get(user=user)
        assert stats.current_streak == -1
        assert stats.best_streak == 2

    def test_win_after_loss_streak_resets_to_one(self):
        user = UserFactory()

        record_bet_result(user, won=False, stake=Decimal("10.00"), payout=Decimal("0"))
        record_bet_result(user, won=False, stake=Decimal("10.00"), payout=Decimal("0"))
        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))

        stats = UserStats.objects.get(user=user)
        assert stats.current_streak == 1
        assert stats.best_streak == 1

    def test_best_streak_preserved_across_loss(self):
        user = UserFactory()

        # Build a 3-win streak
        for _ in range(3):
            record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))
        # Lose, then win 2
        record_bet_result(user, won=False, stake=Decimal("10.00"), payout=Decimal("0"))
        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))
        record_bet_result(user, won=True, stake=Decimal("10.00"), payout=Decimal("20.00"))

        stats = UserStats.objects.get(user=user)
        assert stats.current_streak == 2
        assert stats.best_streak == 3  # preserved from earlier

    def test_cumulative_totals(self):
        user = UserFactory()

        record_bet_result(user, won=True, stake=Decimal("50.00"), payout=Decimal("100.00"))
        record_bet_result(user, won=False, stake=Decimal("25.00"), payout=Decimal("0"))

        stats = UserStats.objects.get(user=user)
        assert stats.total_bets == 2
        assert stats.total_wins == 1
        assert stats.total_losses == 1
        assert stats.total_staked == Decimal("75.00")
        assert stats.total_payout == Decimal("100.00")
        assert stats.net_profit == Decimal("25.00")
