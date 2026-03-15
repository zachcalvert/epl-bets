"""
Tests for Phase 17 badge criteria and awarding logic.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import Mock

import pytest

from betting.badges import (
    BADGE_DEFINITIONS,
    BetContext,
    _called_the_upset,
    _century,
    _first_blood,
    _high_roller,
    _parlay_king,
    _perfect_matchweek,
    _sharp_eye,
    _streak_master,
    _underdog_hunter,
    check_and_award_badges,
)
from betting.tests.factories import (
    BadgeFactory,
    BetSlipFactory,
    ParlayFactory,
    UserBadgeFactory,
    UserStatsFactory,
)
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# ── helpers ──────────────────────────────────────────────────────────────────

def make_ctx(**overrides):
    defaults = {
        "won": True,
        "odds": Decimal("2.00"),
        "is_parlay": False,
        "leg_count": 0,
        "stake": Decimal("10.00"),
        "max_stake": Decimal("100.00"),
    }
    defaults.update(overrides)
    return BetContext(**defaults)


def make_stats(**overrides):
    defaults = {
        "total_bets": 1,
        "total_wins": 1,
        "total_losses": 0,
        "current_streak": 1,
        "best_streak": 1,
    }
    defaults.update(overrides)
    stats = Mock()
    for k, v in defaults.items():
        setattr(stats, k, v)
    stats.win_rate = Decimal("100.0")
    return stats


# ── Criteria unit tests ───────────────────────────────────────────────────────

class TestFirstBlood:
    def test_true_after_first_bet(self):
        assert _first_blood(make_stats(total_bets=1), make_ctx()) is True

    def test_false_before_any_bets(self):
        assert _first_blood(make_stats(total_bets=0), make_ctx()) is False

    def test_true_with_many_bets(self):
        assert _first_blood(make_stats(total_bets=50), make_ctx()) is True


class TestCalledTheUpset:
    def test_true_when_won_with_high_odds(self):
        ctx = make_ctx(won=True, odds=Decimal("4.01"))
        assert _called_the_upset(make_stats(), ctx) is True

    def test_false_when_lost_even_with_high_odds(self):
        ctx = make_ctx(won=False, odds=Decimal("5.00"))
        assert _called_the_upset(make_stats(), ctx) is False

    def test_false_when_odds_exactly_threshold(self):
        ctx = make_ctx(won=True, odds=Decimal("4.00"))
        assert _called_the_upset(make_stats(), ctx) is False

    def test_false_when_odds_below_threshold(self):
        ctx = make_ctx(won=True, odds=Decimal("1.80"))
        assert _called_the_upset(make_stats(), ctx) is False


class TestPerfectMatchweek:
    def test_true_when_won_and_no_losses(self):
        ctx = make_ctx(won=True)
        assert _perfect_matchweek(make_stats(total_losses=0), ctx) is True

    def test_false_when_has_a_loss(self):
        ctx = make_ctx(won=True)
        assert _perfect_matchweek(make_stats(total_losses=1), ctx) is False

    def test_false_when_lost(self):
        ctx = make_ctx(won=False)
        assert _perfect_matchweek(make_stats(total_losses=1), ctx) is False


class TestParlayKing:
    def test_true_when_parlay_won_with_5_legs(self):
        ctx = make_ctx(won=True, is_parlay=True, leg_count=5)
        assert _parlay_king(make_stats(), ctx) is True

    def test_true_with_more_than_5_legs(self):
        ctx = make_ctx(won=True, is_parlay=True, leg_count=8)
        assert _parlay_king(make_stats(), ctx) is True

    def test_false_when_fewer_than_5_legs(self):
        ctx = make_ctx(won=True, is_parlay=True, leg_count=4)
        assert _parlay_king(make_stats(), ctx) is False

    def test_false_when_lost(self):
        ctx = make_ctx(won=False, is_parlay=True, leg_count=5)
        assert _parlay_king(make_stats(), ctx) is False

    def test_false_for_singles(self):
        ctx = make_ctx(won=True, is_parlay=False, leg_count=0)
        assert _parlay_king(make_stats(), ctx) is False


class TestStreakMaster:
    def test_true_when_best_streak_is_10(self):
        assert _streak_master(make_stats(best_streak=10), make_ctx()) is True

    def test_true_when_best_streak_exceeds_10(self):
        assert _streak_master(make_stats(best_streak=15), make_ctx()) is True

    def test_false_when_best_streak_is_9(self):
        assert _streak_master(make_stats(best_streak=9), make_ctx()) is False


class TestHighRoller:
    def test_true_when_won_single_at_max_stake(self):
        ctx = make_ctx(won=True, is_parlay=False, stake=Decimal("1000.00"), max_stake=Decimal("1000.00"))
        assert _high_roller(make_stats(), ctx) is True

    def test_false_when_lost_at_max_stake(self):
        ctx = make_ctx(won=False, is_parlay=False, stake=Decimal("1000.00"), max_stake=Decimal("1000.00"))
        assert _high_roller(make_stats(), ctx) is False

    def test_false_when_below_max_stake(self):
        ctx = make_ctx(won=True, is_parlay=False, stake=Decimal("50.00"), max_stake=Decimal("1000.00"))
        assert _high_roller(make_stats(), ctx) is False

    def test_false_when_parlay_at_max_stake(self):
        ctx = make_ctx(won=True, is_parlay=True, stake=Decimal("1000.00"), max_stake=Decimal("1000.00"))
        assert _high_roller(make_stats(), ctx) is False


class TestSharpEye:
    def test_true_when_qualifies(self):
        stats = make_stats(total_bets=50)
        stats.win_rate = Decimal("60.0")
        assert _sharp_eye(stats, make_ctx()) is True

    def test_false_when_insufficient_bets(self):
        stats = make_stats(total_bets=49)
        stats.win_rate = Decimal("65.0")
        assert _sharp_eye(stats, make_ctx()) is False

    def test_false_when_win_rate_too_low(self):
        stats = make_stats(total_bets=100)
        stats.win_rate = Decimal("59.9")
        assert _sharp_eye(stats, make_ctx()) is False


class TestCentury:
    def test_true_at_100_bets(self):
        assert _century(make_stats(total_bets=100), make_ctx()) is True

    def test_true_above_100_bets(self):
        assert _century(make_stats(total_bets=101), make_ctx()) is True

    def test_false_below_100(self):
        assert _century(make_stats(total_bets=99), make_ctx()) is False


# ── check_and_award_badges integration ───────────────────────────────────────

class TestCheckAndAwardBadges:
    def test_awards_first_blood_on_first_bet(self):
        user = UserFactory()
        BadgeFactory(slug="first_blood")
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = make_ctx(won=True)

        newly_earned = check_and_award_badges(user, stats, ctx)

        slugs = [ub.badge.slug for ub in newly_earned]
        assert "first_blood" in slugs

    def test_does_not_award_same_badge_twice(self):
        user = UserFactory()
        badge = BadgeFactory(slug="first_blood")
        UserBadgeFactory(user=user, badge=badge)
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = make_ctx(won=True)

        newly_earned = check_and_award_badges(user, stats, ctx)

        assert all(ub.badge.slug != "first_blood" for ub in newly_earned)

    def test_returns_empty_when_no_badges_defined(self):
        user = UserFactory()
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = make_ctx(won=True)

        # No Badge rows exist
        newly_earned = check_and_award_badges(user, stats, ctx)

        assert newly_earned == []

    def test_swallows_criterion_errors(self, monkeypatch):
        """A broken criterion should not abort badge checking."""
        user = UserFactory()
        BadgeFactory(slug="first_blood")
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = make_ctx(won=True)

        def exploding_criterion(stats, ctx):
            raise RuntimeError("boom")

        from betting import badges as badges_module
        original = badges_module.CRITERIA[:]
        badges_module.CRITERIA.insert(0, ("first_blood", exploding_criterion))
        try:
            # Should not raise
            check_and_award_badges(user, stats, ctx)
        finally:
            badges_module.CRITERIA[:] = original

    def test_awards_multiple_badges_in_one_call(self):
        user = UserFactory()
        BadgeFactory(slug="first_blood")
        BadgeFactory(slug="century")
        stats = UserStatsFactory(user=user, total_bets=100)
        ctx = make_ctx(won=True)

        newly_earned = check_and_award_badges(user, stats, ctx)

        slugs = {ub.badge.slug for ub in newly_earned}
        assert "first_blood" in slugs
        assert "century" in slugs


# ── BADGE_DEFINITIONS sanity ──────────────────────────────────────────────────

class TestBadgeDefinitions:
    def test_all_slugs_unique(self):
        slugs = [d["slug"] for d in BADGE_DEFINITIONS]
        assert len(slugs) == len(set(slugs))

    def test_all_rarities_valid(self):
        valid = {"common", "uncommon", "rare", "epic"}
        for defn in BADGE_DEFINITIONS:
            assert defn["rarity"] in valid, f"{defn['slug']} has invalid rarity"

    def test_all_fields_present(self):
        required = {"slug", "name", "description", "icon", "rarity"}
        for defn in BADGE_DEFINITIONS:
            assert required.issubset(defn.keys()), f"Missing fields in {defn['slug']}"


# ── record_bet_result broadcasts badges ──────────────────────────────────────

class TestRecordBetResultBadgeBroadcast:
    @pytest.mark.django_db(transaction=True)
    def test_broadcasts_badge_after_first_bet(self, monkeypatch):
        from betting.stats import record_bet_result

        user = UserFactory()
        BadgeFactory(slug="first_blood")

        sent = []

        class FakeLayer:
            async def group_send(self, group, event):
                sent.append((group, event))

        monkeypatch.setattr("betting.stats.get_channel_layer", lambda: FakeLayer())

        record_bet_result(
            user, won=True, stake=Decimal("10"), payout=Decimal("20"),
            odds=Decimal("2.00"),
        )

        assert len(sent) == 1
        assert sent[0][0] == f"user_notifications_{user.pk}"
        assert sent[0][1]["type"] == "badge_notification"

    @pytest.mark.django_db(transaction=True)
    def test_no_broadcast_when_no_badge_earned(self, monkeypatch):
        from betting.stats import record_bet_result

        user = UserFactory()
        # No badges seeded — nothing to earn

        sent = []

        class FakeLayer:
            async def group_send(self, group, event):
                sent.append((group, event))

        monkeypatch.setattr("betting.stats.get_channel_layer", lambda: FakeLayer())

        record_bet_result(
            user, won=True, stake=Decimal("10"), payout=Decimal("20"),
        )

        assert sent == []


# ── badge_notification consumer handler ──────────────────────────────────────

class TestBadgeNotificationConsumer:
    def test_badge_notification_renders_and_sends(self, monkeypatch):
        from unittest.mock import Mock

        from rewards.consumers import NotificationConsumer

        user = UserBadgeFactory().user
        user_badge = user.badges.select_related("badge").first()

        consumer = NotificationConsumer()
        consumer.scope = {"user": user}
        consumer.channel_name = "test-channel"
        consumer.send = Mock()

        monkeypatch.setattr("rewards.consumers.close_old_connections", lambda: None)
        monkeypatch.setattr(
            "rewards.consumers.render_to_string",
            lambda template, context: f"{template}:{context['user_badge'].pk}",
        )

        consumer.badge_notification({"user_badge_id": user_badge.pk})

        consumer.send.assert_called_once()
        text = consumer.send.call_args.kwargs["text_data"]
        assert "betting/partials/badge_toast_oob.html" in text
        assert str(user_badge.pk) in text

    def test_badge_notification_swallows_render_errors(self, monkeypatch):
        from unittest.mock import Mock

        from rewards.consumers import NotificationConsumer

        ub = UserBadgeFactory()

        consumer = NotificationConsumer()
        consumer.scope = {"user": ub.user}
        consumer.channel_name = "test-channel"
        consumer.send = Mock()

        monkeypatch.setattr("rewards.consumers.close_old_connections", lambda: None)
        monkeypatch.setattr(
            "rewards.consumers.render_to_string",
            Mock(side_effect=RuntimeError("render error")),
        )

        # Should not raise
        consumer.badge_notification({"user_badge_id": ub.pk})

        consumer.send.assert_not_called()

    def test_badge_notification_ignores_wrong_user(self, monkeypatch):
        from unittest.mock import Mock

        from rewards.consumers import NotificationConsumer

        ub = UserBadgeFactory()
        other_user = UserFactory()

        consumer = NotificationConsumer()
        consumer.scope = {"user": other_user}
        consumer.channel_name = "test-channel"
        consumer.send = Mock()

        monkeypatch.setattr("rewards.consumers.close_old_connections", lambda: None)

        consumer.badge_notification({"user_badge_id": ub.pk})

        consumer.send.assert_not_called()


# ── _underdog_hunter DB queries ───────────────────────────────────────────────

class TestUnderdogHunter:
    def test_true_when_10_single_upset_wins(self):
        user = UserFactory()
        stats = UserStatsFactory(user=user)
        stats.user = user
        for _ in range(10):
            BetSlipFactory(
                user=user,
                status="WON",
                odds_at_placement="4.50",
            )
        ctx = make_ctx(won=True, odds=Decimal("4.50"))
        assert _underdog_hunter(stats, ctx) is True

    def test_false_below_threshold(self):
        user = UserFactory()
        stats = UserStatsFactory(user=user)
        stats.user = user
        for _ in range(9):
            BetSlipFactory(user=user, status="WON", odds_at_placement="4.50")
        ctx = make_ctx(won=True)
        assert _underdog_hunter(stats, ctx) is False

    def test_counts_parlay_upsets(self):
        user = UserFactory()
        stats = UserStatsFactory(user=user)
        stats.user = user
        for _ in range(5):
            BetSlipFactory(user=user, status="WON", odds_at_placement="4.50")
        for _ in range(5):
            ParlayFactory(user=user, status="WON", combined_odds="5.00")
        ctx = make_ctx(won=True)
        assert _underdog_hunter(stats, ctx) is True


# ── check_and_award_badges: all-earned early return ───────────────────────────

class TestCheckAndAwardBadgesEarlyReturn:
    def test_returns_empty_when_all_badges_already_earned(self):
        user = UserFactory()
        badge = BadgeFactory(slug="first_blood")
        UserBadgeFactory(user=user, badge=badge)
        stats = UserStatsFactory(user=user, total_bets=1)
        ctx = make_ctx(won=True)

        # Only one badge in DB and user already has it — hits the `not candidate_slugs` path
        newly_earned = check_and_award_badges(user, stats, ctx)

        assert newly_earned == []


# ── _broadcast_badges exception handler ──────────────────────────────────────

class TestBroadcastBadgesErrorHandler:
    @pytest.mark.django_db(transaction=True)
    def test_swallows_channel_layer_error(self, monkeypatch):
        from betting.stats import record_bet_result

        user = UserFactory()
        BadgeFactory(slug="first_blood")

        class BrokenLayer:
            async def group_send(self, group, event):
                raise RuntimeError("channel layer down")

        monkeypatch.setattr("betting.stats.get_channel_layer", lambda: BrokenLayer())

        # Should not raise even when channel layer is broken
        record_bet_result(
            user, won=True, stake=Decimal("10"), payout=Decimal("20"),
        )


# ── seed_badges management command ───────────────────────────────────────────

class TestSeedBadgesCommand:
    def test_creates_all_badge_definitions(self):
        from django.core.management import call_command

        from betting.models import Badge

        out = StringIO()
        call_command("seed_badges", stdout=out)

        assert Badge.objects.count() == len(BADGE_DEFINITIONS)

    def test_idempotent_on_second_run(self):
        from django.core.management import call_command

        from betting.models import Badge

        call_command("seed_badges", stdout=StringIO())
        call_command("seed_badges", stdout=StringIO())

        assert Badge.objects.count() == len(BADGE_DEFINITIONS)

    def test_output_reports_created_and_updated(self):
        from django.core.management import call_command

        out = StringIO()
        call_command("seed_badges", stdout=out)
        output = out.getvalue()

        assert "Created" in output or "Updated" in output
        assert "Done" in output


# ── tasks: no-legs parlay and PENDING+VOID paths ─────────────────────────────

class TestEvaluateParlayEdgeCases:
    @pytest.mark.django_db(transaction=True)
    def test_parlay_with_no_legs_marked_lost(self, monkeypatch):
        from betting.tasks import _evaluate_parlay

        user = UserFactory()
        from betting.models import UserBalance
        UserBalance.objects.create(user=user, balance=Decimal("1000"))
        parlay = ParlayFactory(user=user, stake=Decimal("10"), combined_odds="3.00")
        # No legs created

        monkeypatch.setattr(
            "betting.tasks.record_bet_result",
            lambda *a, **kw: None,
        )

        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        assert parlay.status == "LOST"
        assert parlay.payout == Decimal("0")

    @pytest.mark.django_db(transaction=True)
    def test_parlay_recalculates_odds_when_pending_leg_voided(self, monkeypatch):
        from betting.tasks import _evaluate_parlay
        from betting.tests.factories import ParlayLegFactory

        user = UserFactory()
        from betting.models import UserBalance
        UserBalance.objects.create(user=user, balance=Decimal("1000"))
        parlay = ParlayFactory(user=user, stake=Decimal("10"), combined_odds="6.00")

        ParlayLegFactory(parlay=parlay, odds_at_placement="2.00", status="WON")
        ParlayLegFactory(parlay=parlay, odds_at_placement="3.00", status="PENDING")
        ParlayLegFactory(parlay=parlay, odds_at_placement="2.00", status="VOID")

        # Still has a PENDING leg — should recalc combined_odds but not settle
        _evaluate_parlay(parlay.pk)

        parlay.refresh_from_db()
        assert parlay.status == "PENDING"
        # odds should now reflect only the active (non-void) legs: 2.00 * 3.00 = 6.00
        # leg1(WON)=2.00, leg2(PENDING)=3.00 — void leg excluded
        assert parlay.combined_odds == Decimal("6.00")
