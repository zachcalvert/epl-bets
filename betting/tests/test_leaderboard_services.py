from decimal import Decimal

import pytest

from betting.services import (
    BOARD_TYPES,
    WIN_RATE_MIN_BETS,
    get_leaderboard_entries,
    get_user_rank,
)
from betting.tests.factories import UserBalanceFactory, UserStatsFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestBoardTypes:
    def test_board_types_tuple(self):
        assert BOARD_TYPES == ("balance", "profit", "win_rate", "streak")


class TestBalanceLeaderboard:
    def test_returns_entries_ordered_by_balance_desc(self):
        UserBalanceFactory(balance="500.00")
        UserBalanceFactory(balance="1500.00")
        UserBalanceFactory(balance="800.00")

        entries = get_leaderboard_entries(board_type="balance")

        balances = [e.balance for e in entries]
        assert balances == [Decimal("1500.00"), Decimal("800.00"), Decimal("500.00")]

    def test_limit_restricts_count(self):
        for _ in range(5):
            UserBalanceFactory()

        entries = get_leaderboard_entries(limit=3, board_type="balance")

        assert len(entries) == 3

    def test_entries_have_display_identity(self):
        UserBalanceFactory(user=UserFactory(display_name="TestPlayer"))

        entries = get_leaderboard_entries(board_type="balance")

        assert entries[0].display_identity == "TestPlayer"


class TestProfitLeaderboard:
    def test_returns_entries_ordered_by_net_profit_desc(self):
        UserStatsFactory(total_bets=5, net_profit="200.00")
        UserStatsFactory(total_bets=5, net_profit="-50.00")
        UserStatsFactory(total_bets=5, net_profit="500.00")

        entries = get_leaderboard_entries(board_type="profit")

        profits = [e.net_profit for e in entries]
        assert profits == [Decimal("500.00"), Decimal("200.00"), Decimal("-50.00")]

    def test_excludes_users_with_no_bets(self):
        UserStatsFactory(total_bets=0, net_profit="0.00")
        UserStatsFactory(total_bets=3, net_profit="100.00")

        entries = get_leaderboard_entries(board_type="profit")

        assert len(entries) == 1


class TestWinRateLeaderboard:
    def test_returns_entries_ordered_by_win_rate_desc(self):
        UserStatsFactory(total_bets=20, total_wins=10)  # 50%
        UserStatsFactory(total_bets=10, total_wins=8)  # 80%
        UserStatsFactory(total_bets=15, total_wins=9)  # 60%

        entries = get_leaderboard_entries(board_type="win_rate")

        # 80%, 60%, 50%
        assert len(entries) == 3
        assert entries[0].total_wins == 8
        assert entries[1].total_wins == 9
        assert entries[2].total_wins == 10

    def test_excludes_users_below_min_bets(self):
        UserStatsFactory(total_bets=WIN_RATE_MIN_BETS - 1, total_wins=5)
        UserStatsFactory(total_bets=WIN_RATE_MIN_BETS, total_wins=8)

        entries = get_leaderboard_entries(board_type="win_rate")

        assert len(entries) == 1


class TestStreakLeaderboard:
    def test_returns_entries_ordered_by_best_streak_desc(self):
        UserStatsFactory(total_bets=10, best_streak=3, current_streak=1)
        UserStatsFactory(total_bets=10, best_streak=7, current_streak=-2)
        UserStatsFactory(total_bets=10, best_streak=5, current_streak=5)

        entries = get_leaderboard_entries(board_type="streak")

        streaks = [e.best_streak for e in entries]
        assert streaks == [7, 5, 3]

    def test_excludes_users_with_no_bets(self):
        UserStatsFactory(total_bets=0, best_streak=0)
        UserStatsFactory(total_bets=5, best_streak=3)

        entries = get_leaderboard_entries(board_type="streak")

        assert len(entries) == 1


class TestGetUserRank:
    def test_returns_none_for_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser

        assert get_user_rank(AnonymousUser()) is None

    def test_returns_none_when_user_in_leaderboard(self):
        ub = UserBalanceFactory(balance="1000.00")
        leaderboard = get_leaderboard_entries(board_type="balance")

        rank = get_user_rank(ub.user, leaderboard, board_type="balance")

        assert rank is None  # already visible in leaderboard

    def test_balance_rank_computed_correctly(self):
        UserBalanceFactory(balance="2000.00")
        UserBalanceFactory(balance="1500.00")
        ub_low = UserBalanceFactory(balance="500.00")

        leaderboard = get_leaderboard_entries(limit=2, board_type="balance")
        rank = get_user_rank(ub_low.user, leaderboard, board_type="balance")

        assert rank is not None
        assert rank.rank == 3

    def test_profit_rank_computed_correctly(self):
        UserStatsFactory(total_bets=5, net_profit="500.00")
        UserStatsFactory(total_bets=5, net_profit="200.00")
        stats_low = UserStatsFactory(total_bets=5, net_profit="50.00")

        leaderboard = get_leaderboard_entries(limit=2, board_type="profit")
        rank = get_user_rank(stats_low.user, leaderboard, board_type="profit")

        assert rank is not None
        assert rank.rank == 3

    def test_streak_rank_computed_correctly(self):
        UserStatsFactory(total_bets=10, best_streak=10)
        UserStatsFactory(total_bets=10, best_streak=5)
        stats_low = UserStatsFactory(total_bets=10, best_streak=2)

        leaderboard = get_leaderboard_entries(limit=2, board_type="streak")
        rank = get_user_rank(stats_low.user, leaderboard, board_type="streak")

        assert rank is not None
        assert rank.rank == 3

    def test_returns_none_for_user_without_balance(self):
        user = UserFactory()

        rank = get_user_rank(user, board_type="balance")

        assert rank is None

    def test_returns_none_for_user_without_stats(self):
        user = UserFactory()

        rank = get_user_rank(user, board_type="profit")

        assert rank is None

    def test_win_rate_rank_returns_none_below_min_bets(self):
        stats = UserStatsFactory(total_bets=WIN_RATE_MIN_BETS - 1, total_wins=5)

        rank = get_user_rank(stats.user, board_type="win_rate")

        assert rank is None
