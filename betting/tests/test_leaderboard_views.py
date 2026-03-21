from decimal import Decimal

import pytest
from django.urls import reverse

from betting.tests.factories import UserBalanceFactory, UserStatsFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestLeaderboardViewTabs:
    def test_default_board_type_is_balance(self, client):
        UserBalanceFactory()

        response = client.get(reverse("matches:leaderboard"))

        assert response.status_code == 200
        assert response.context["board_type"] == "balance"

    def test_profit_board_type(self, client):
        UserStatsFactory(total_bets=5, net_profit="100.00")

        response = client.get(reverse("matches:leaderboard"), {"type": "profit"})

        assert response.status_code == 200
        assert response.context["board_type"] == "profit"
        assert len(response.context["leaderboard"]) == 1

    def test_win_rate_board_type(self, client):
        UserStatsFactory(total_bets=10, total_wins=7)

        response = client.get(reverse("matches:leaderboard"), {"type": "win_rate"})

        assert response.status_code == 200
        assert response.context["board_type"] == "win_rate"

    def test_streak_board_type(self, client):
        UserStatsFactory(total_bets=10, best_streak=5)

        response = client.get(reverse("matches:leaderboard"), {"type": "streak"})

        assert response.status_code == 200
        assert response.context["board_type"] == "streak"

    def test_invalid_board_type_falls_back_to_balance(self, client):
        UserBalanceFactory()

        response = client.get(reverse("matches:leaderboard"), {"type": "invalid"})

        assert response.status_code == 200
        assert response.context["board_type"] == "balance"

    def test_htmx_request_returns_partial_template(self, client):
        UserBalanceFactory()

        response = client.get(
            reverse("matches:leaderboard"),
            {"type": "profit"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert any(
            t.name == "matches/partials/leaderboard_table.html"
            for t in response.templates
        )

    def test_full_page_includes_all_board_types_in_context(self, client):
        response = client.get(reverse("matches:leaderboard"))

        assert response.context["board_types"] == ("balance", "profit", "win_rate", "streak")


class TestProfileView:
    def test_profile_renders_for_user_with_stats(self, client):
        stats = UserStatsFactory(
            total_bets=20,
            total_wins=12,
            total_losses=8,
            net_profit="150.00",
            best_streak=5,
            current_streak=2,
            user__display_name="SharpShooter",
        )
        UserBalanceFactory(user=stats.user, balance="1150.00")

        response = client.get(reverse("profile", args=[stats.user.slug]))

        assert response.status_code == 200
        assert response.context["display_identity"] == "SharpShooter"
        assert response.context["stats"] == stats
        assert response.context["balance"] == Decimal("1150.00")

    def test_profile_renders_for_user_without_stats(self, client):
        user = UserFactory()
        UserBalanceFactory(user=user)

        response = client.get(reverse("profile", args=[user.slug]))

        assert response.status_code == 200
        assert response.context["stats"] is None

    def test_profile_returns_404_for_nonexistent_user(self, client):
        response = client.get(reverse("profile", args=["no-such-user-xYz12345"]))

        assert response.status_code == 404

    def test_profile_shows_recent_bets(self, client):
        from betting.models import BetSlip
        from betting.tests.factories import BetSlipFactory

        user = UserFactory()
        UserBalanceFactory(user=user)
        bet = BetSlipFactory(user=user, status=BetSlip.Status.WON, payout="21.00")

        response = client.get(reverse("profile", args=[user.slug]))

        assert response.status_code == 200
        assert bet in response.context["recent_bets"]

    def test_profile_excludes_pending_bets(self, client):
        from betting.models import BetSlip
        from betting.tests.factories import BetSlipFactory

        user = UserFactory()
        UserBalanceFactory(user=user)
        BetSlipFactory(user=user, status=BetSlip.Status.PENDING)

        response = client.get(reverse("profile", args=[user.slug]))

        assert len(response.context["recent_bets"]) == 0

    def test_profile_shows_recent_comments(self, client):
        from discussions.tests.factories import CommentFactory

        user = UserFactory()
        UserBalanceFactory(user=user)
        comment = CommentFactory(user=user)

        response = client.get(reverse("profile", args=[user.slug]))

        assert response.status_code == 200
        assert comment in response.context["recent_comments"]

    def test_profile_excludes_deleted_comments(self, client):
        from discussions.tests.factories import CommentFactory

        user = UserFactory()
        UserBalanceFactory(user=user)
        CommentFactory(user=user, is_deleted=True)

        response = client.get(reverse("profile", args=[user.slug]))

        assert len(response.context["recent_comments"]) == 0

    def test_profile_comments_ordered_newest_first(self, client):
        from discussions.tests.factories import CommentFactory

        user = UserFactory()
        UserBalanceFactory(user=user)
        comment1 = CommentFactory(user=user)
        comment2 = CommentFactory(user=user)

        response = client.get(reverse("profile", args=[user.slug]))

        comments = list(response.context["recent_comments"])
        assert comments[0] == comment2
        assert comments[1] == comment1
