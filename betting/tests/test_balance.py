"""Tests for balance transaction logging: log_transaction(), BalanceHistoryAPI,
and all instrumented balance modification points."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from betting.balance import log_transaction
from betting.models import (
    BalanceTransaction,
    BetSlip,
    Parlay,
)
from betting.tasks import settle_match_bets
from betting.tests.factories import (
    BetSlipFactory,
    OddsFactory,
    ParlayFactory,
    ParlayLegFactory,
    UserBalanceFactory,
)
from bots.services import maybe_topup_bot, place_bot_bet, place_bot_parlay
from bots.tests.factories import BotUserFactory
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


# ── log_transaction helper ────────────────────────────────────────────────────

class TestLogTransaction:
    def test_increments_balance(self):
        ub = UserBalanceFactory(balance="500.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("100.00"), BalanceTransaction.Type.REWARD)
        ub.refresh_from_db()
        assert ub.balance == Decimal("600.00")

    def test_decrements_balance(self):
        ub = UserBalanceFactory(balance="500.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("-50.00"), BalanceTransaction.Type.BET_PLACEMENT)
        ub.refresh_from_db()
        assert ub.balance == Decimal("450.00")

    def test_creates_transaction_record(self):
        ub = UserBalanceFactory(balance="1000.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("250.00"), BalanceTransaction.Type.BET_WIN, "Bet abc won")

        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.amount == Decimal("250.00")
        assert tx.balance_after == Decimal("1250.00")
        assert tx.transaction_type == BalanceTransaction.Type.BET_WIN
        assert tx.description == "Bet abc won"

    def test_balance_after_reflects_new_balance(self):
        ub = UserBalanceFactory(balance="300.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("-100.00"), BalanceTransaction.Type.BET_PLACEMENT)

        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.balance_after == Decimal("200.00")

    def test_multiple_transactions_track_running_balance(self):
        ub = UserBalanceFactory(balance="1000.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("-200.00"), BalanceTransaction.Type.BET_PLACEMENT)
        log_transaction(ub, Decimal("500.00"), BalanceTransaction.Type.BET_WIN)

        txns = list(BalanceTransaction.objects.filter(user=ub.user).order_by("created_at"))
        assert txns[0].balance_after == Decimal("800.00")
        assert txns[1].balance_after == Decimal("1300.00")

    def test_description_defaults_to_empty_string(self):
        ub = UserBalanceFactory(balance="1000.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("50.00"), BalanceTransaction.Type.REWARD)

        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.description == ""


# ── BalanceHistoryAPI view ────────────────────────────────────────────────────

class TestBalanceHistoryAPI:
    def test_requires_login(self, client):
        user = UserFactory()
        response = client.get(reverse("balance_history_api", args=[user.slug]))
        assert response.status_code == 302

    def test_returns_403_for_other_user(self, client):
        user = UserFactory()
        other = UserFactory()
        client.force_login(user)

        response = client.get(reverse("balance_history_api", args=[other.slug]))

        assert response.status_code == 403

    def test_returns_single_point_for_user_with_only_todays_transactions(self, client):
        user = UserFactory()
        ub = UserBalanceFactory(user=user, balance="1000.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("500.00"), BalanceTransaction.Type.BET_WIN)
        client.force_login(user)

        response = client.get(reverse("balance_history_api", args=[user.slug]))

        assert response.status_code == 200
        data = json.loads(response.content)["data"]
        # Only today has a transaction; no carry-backward into days with no history
        assert len(data) == 1
        assert data[0]["y"] == 1500.0

    def test_carries_forward_balance_on_days_with_no_activity(self, client):
        user = UserFactory()
        ub = UserBalanceFactory(user=user, balance="1000.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("200.00"), BalanceTransaction.Type.BET_WIN)
        # Backdate the transaction so it falls outside today — 5 days ago
        five_days_ago = timezone.now() - timedelta(days=5)
        BalanceTransaction.objects.filter(user=user).update(created_at=five_days_ago)
        client.force_login(user)

        response = client.get(reverse("balance_history_api", args=[user.slug]))

        data = json.loads(response.content)["data"]
        # Should have 6 points (day -5 through today), each carrying forward 1200
        assert len(data) == 6
        assert all(point["y"] == 1200.0 for point in data)

    def test_returns_chronological_dates(self, client):
        user = UserFactory()
        ub = UserBalanceFactory(user=user, balance="800.00")
        ub.refresh_from_db()
        log_transaction(ub, Decimal("-200.00"), BalanceTransaction.Type.BET_PLACEMENT)
        log_transaction(ub, Decimal("420.00"), BalanceTransaction.Type.BET_WIN)
        client.force_login(user)

        response = client.get(reverse("balance_history_api", args=[user.slug]))

        data = json.loads(response.content)["data"]
        dates = [p["t"] for p in data]
        assert dates == sorted(dates)
        assert data[-1]["y"] == 1020.0

    def test_returns_empty_list_when_no_transactions(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(reverse("balance_history_api", args=[user.slug]))

        assert response.status_code == 200
        assert json.loads(response.content)["data"] == []


# ── Bet placement instrumentation ────────────────────────────────────────────

class TestBetPlacementLogsTransaction:
    def test_place_bet_creates_placement_transaction(self, client):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="100.00")
        match = MatchFactory()
        OddsFactory(match=match, home_win="2.10")
        client.force_login(user)

        client.post(
            reverse("betting:place_bet", args=[match.slug]),
            data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
        )

        tx = BalanceTransaction.objects.get(user=user)
        assert tx.transaction_type == BalanceTransaction.Type.BET_PLACEMENT
        assert tx.amount == Decimal("-10.00")
        assert tx.balance_after == Decimal("90.00")

    def test_parlay_placement_creates_transaction(self, client):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="500.00")
        m1, m2 = MatchFactory(), MatchFactory()
        OddsFactory(match=m1, home_win="2.00")
        OddsFactory(match=m2, away_win="3.00")
        client.force_login(user)

        session = client.session
        session["parlay_slip"] = [
            {"match_id": m1.pk, "selection": "HOME_WIN"},
            {"match_id": m2.pk, "selection": "AWAY_WIN"},
        ]
        session.save()

        client.post(
            reverse("betting:parlay_place"),
            data={"stake": "25.00"},
        )

        tx = BalanceTransaction.objects.get(user=user)
        assert tx.transaction_type == BalanceTransaction.Type.PARLAY_PLACEMENT
        assert tx.amount == Decimal("-25.00")
        assert tx.balance_after == Decimal("475.00")


# ── Settlement instrumentation ────────────────────────────────────────────────

class TestSettlementLogsTransactions:
    def test_winning_bet_creates_win_transaction(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=2, away_score=0)
        ub = UserBalanceFactory(balance="100.00")
        BetSlipFactory(
            user=ub.user, match=match,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement="2.50", stake="10.00",
        )

        settle_match_bets.run(match.pk)

        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.transaction_type == BalanceTransaction.Type.BET_WIN
        assert tx.amount == Decimal("25.00")
        assert tx.balance_after == Decimal("125.00")

    def test_losing_bet_creates_no_transaction(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=1)
        ub = UserBalanceFactory(balance="100.00")
        BetSlipFactory(
            user=ub.user, match=match,
            selection=BetSlip.Selection.HOME_WIN,
            stake="10.00",
        )

        settle_match_bets.run(match.pk)

        assert BalanceTransaction.objects.filter(user=ub.user).count() == 0

    def test_voided_bet_creates_void_transaction(self):
        match = MatchFactory(status=Match.Status.CANCELLED)
        ub = UserBalanceFactory(balance="100.00")
        BetSlipFactory(user=ub.user, match=match, stake="15.00")

        settle_match_bets.run(match.pk)

        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.transaction_type == BalanceTransaction.Type.BET_VOID
        assert tx.amount == Decimal("15.00")
        assert tx.balance_after == Decimal("115.00")

    def test_winning_parlay_creates_win_transaction(self):
        match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
        ub = UserBalanceFactory(balance="500.00")
        parlay = ParlayFactory(user=ub.user, stake="20.00", combined_odds="4.00")
        ParlayLegFactory(
            parlay=parlay, match=match,
            selection=BetSlip.Selection.HOME_WIN,
        )

        settle_match_bets.run(match.pk)

        parlay.refresh_from_db()
        assert parlay.status == Parlay.Status.WON
        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.transaction_type == BalanceTransaction.Type.PARLAY_WIN
        assert tx.amount == parlay.payout

    def test_fully_voided_parlay_creates_void_transaction(self):
        match = MatchFactory(status=Match.Status.CANCELLED)
        ub = UserBalanceFactory(balance="500.00")
        parlay = ParlayFactory(user=ub.user, stake="30.00", combined_odds="3.00")
        ParlayLegFactory(
            parlay=parlay, match=match,
            selection=BetSlip.Selection.HOME_WIN,
        )

        settle_match_bets.run(match.pk)

        parlay.refresh_from_db()
        assert parlay.status == Parlay.Status.VOID
        tx = BalanceTransaction.objects.get(user=ub.user)
        assert tx.transaction_type == BalanceTransaction.Type.PARLAY_VOID
        assert tx.amount == Decimal("30.00")
        assert tx.balance_after == Decimal("530.00")


# ── Bailout instrumentation ───────────────────────────────────────────────────

class TestBailoutLogsTransaction:
    def test_bailout_creates_transaction(self, client):
        user = UserFactory()
        UserBalanceFactory(user=user, balance="0.00")
        client.force_login(user)

        response = client.post(reverse("betting:bailout"))

        assert response.status_code == 200
        tx = BalanceTransaction.objects.get(user=user)
        assert tx.transaction_type == BalanceTransaction.Type.BAILOUT
        assert tx.amount > 0
        assert tx.balance_after == tx.amount


# ── Signup instrumentation ───────────────────────────────────────────────────

class TestSignupLogsTransaction:
    def test_registration_creates_signup_transaction(self, client, django_user_model):
        response = client.post(
            reverse("website:signup"),
            data={
                "email": "newuser@example.com",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )

        assert response.status_code == 302
        user = django_user_model.objects.get(email="newuser@example.com")
        tx = BalanceTransaction.objects.get(user=user)
        assert tx.transaction_type == BalanceTransaction.Type.SIGNUP
        assert tx.amount == Decimal("1000.00")
        assert tx.balance_after == Decimal("1000.00")


# ── Bot service instrumentation ───────────────────────────────────────────────

class TestBotServicesLogTransactions:
    def test_place_bot_bet_creates_placement_transaction(self):
        bot = BotUserFactory()
        ub = UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win="2.10")

        place_bot_bet(bot, match.pk, "HOME_WIN", Decimal("50.00"))

        tx = BalanceTransaction.objects.get(user=bot)
        assert tx.transaction_type == BalanceTransaction.Type.BET_PLACEMENT
        assert tx.amount == Decimal("-50.00")
        ub.refresh_from_db()
        assert tx.balance_after == ub.balance

    def test_place_bot_parlay_creates_placement_transaction(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="500.00")
        m1, m2 = MatchFactory(status=Match.Status.SCHEDULED), MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1, home_win="2.00")
        OddsFactory(match=m2, away_win="3.00")

        place_bot_parlay(
            bot,
            [{"match_id": m1.pk, "selection": "HOME_WIN"}, {"match_id": m2.pk, "selection": "AWAY_WIN"}],
            Decimal("20.00"),
        )

        tx = BalanceTransaction.objects.get(user=bot)
        assert tx.transaction_type == BalanceTransaction.Type.PARLAY_PLACEMENT
        assert tx.amount == Decimal("-20.00")

    def test_maybe_topup_bot_creates_bailout_transaction(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot, balance="10.00")

        maybe_topup_bot(bot, min_balance=Decimal("50.00"))

        tx = BalanceTransaction.objects.get(user=bot)
        assert tx.transaction_type == BalanceTransaction.Type.BAILOUT
        assert tx.amount > 0


# ── Account page chart ───────────────────────────────────────────────────────

class TestAccountChart:
    def test_account_page_shows_chart(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(reverse("website:account"))

        assert response.status_code == 200
        assert b"balanceChart" in response.content

    def test_profile_page_does_not_show_chart(self, client):
        user = UserFactory()
        client.force_login(user)

        response = client.get(reverse("profile", args=[user.slug]))

        assert response.status_code == 200
        assert b"balanceChart" not in response.content
