from decimal import Decimal

import pytest

from betting.tests.factories import UserStatsFactory

pytestmark = pytest.mark.django_db


def test_user_stats_str_shows_record_and_profit():
    stats = UserStatsFactory(total_wins=5, total_losses=3, net_profit="120.50")

    result = str(stats)

    assert "5W-3L" in result
    assert "+120.50" in result


def test_user_stats_str_shows_negative_profit():
    stats = UserStatsFactory(total_wins=1, total_losses=4, net_profit="-30.00")

    assert "-30.00" in str(stats)


def test_win_rate_with_bets():
    stats = UserStatsFactory(total_bets=10, total_wins=7)

    assert stats.win_rate == Decimal("70.0")


def test_win_rate_with_no_bets():
    stats = UserStatsFactory(total_bets=0, total_wins=0)

    assert stats.win_rate == Decimal("0.00")


def test_win_rate_rounds_to_one_decimal():
    stats = UserStatsFactory(total_bets=3, total_wins=1)

    assert stats.win_rate == Decimal("33.3")
