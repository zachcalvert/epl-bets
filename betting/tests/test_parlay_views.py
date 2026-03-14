from decimal import Decimal

import pytest
from django.urls import reverse

from betting.models import BetSlip, Parlay, ParlayLeg, UserBalance
from betting.tests.factories import OddsFactory, ParlayFactory, ParlayLegFactory, UserBalanceFactory
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

PARLAY_SESSION_KEY = "parlay_slip"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _login(client, user=None):
    if user is None:
        user = UserFactory()
    client.force_login(user)
    return user


def _slip(client):
    return client.session.get(PARLAY_SESSION_KEY, [])


# ── Add to parlay ─────────────────────────────────────────────────────────────

class TestAddToParlayView:
    def test_add_leg_to_empty_slip(self, client):
        user = _login(client)
        match = MatchFactory(status=Match.Status.SCHEDULED)

        resp = client.post(reverse("betting:parlay_add"), {
            "match_id": match.pk,
            "selection": "HOME_WIN",
        })

        assert resp.status_code == 200
        slip = _slip(client)
        assert len(slip) == 1
        assert slip[0]["match_id"] == match.pk
        assert slip[0]["selection"] == "HOME_WIN"

    def test_add_two_different_matches(self, client):
        _login(client)
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)

        client.post(reverse("betting:parlay_add"), {"match_id": m1.pk, "selection": "HOME_WIN"})
        client.post(reverse("betting:parlay_add"), {"match_id": m2.pk, "selection": "DRAW"})

        slip = _slip(client)
        assert len(slip) == 2

    def test_duplicate_match_rejected(self, client):
        _login(client)
        match = MatchFactory(status=Match.Status.SCHEDULED)

        client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "HOME_WIN"})
        resp = client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "DRAW"})

        assert resp.status_code == 200
        assert len(_slip(client)) == 1
        assert b"already in your parlay" in resp.content

    def test_finished_match_rejected(self, client):
        _login(client)
        match = MatchFactory(status=Match.Status.FINISHED)

        resp = client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "HOME_WIN"})

        assert resp.status_code == 200
        assert len(_slip(client)) == 0
        assert b"not available for betting" in resp.content

    def test_invalid_selection_rejected(self, client):
        _login(client)
        match = MatchFactory(status=Match.Status.SCHEDULED)

        resp = client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "INVALID"})

        assert resp.status_code == 200
        assert len(_slip(client)) == 0

    def test_requires_authentication(self, client):
        match = MatchFactory(status=Match.Status.SCHEDULED)
        resp = client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "HOME_WIN"})
        assert resp.status_code == 302  # redirect to login


# ── Remove from parlay ────────────────────────────────────────────────────────

class TestRemoveFromParlayView:
    def test_remove_leg(self, client):
        _login(client)
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)

        client.post(reverse("betting:parlay_add"), {"match_id": m1.pk, "selection": "HOME_WIN"})
        client.post(reverse("betting:parlay_add"), {"match_id": m2.pk, "selection": "DRAW"})

        client.post(reverse("betting:parlay_remove"), {"match_id": m1.pk})

        slip = _slip(client)
        assert len(slip) == 1
        assert slip[0]["match_id"] == m2.pk

    def test_remove_nonexistent_leg_is_noop(self, client):
        _login(client)
        match = MatchFactory(status=Match.Status.SCHEDULED)
        client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "HOME_WIN"})

        client.post(reverse("betting:parlay_remove"), {"match_id": 9999999})

        assert len(_slip(client)) == 1


# ── Clear parlay ──────────────────────────────────────────────────────────────

class TestClearParlayView:
    def test_clear_empties_slip(self, client):
        _login(client)
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        client.post(reverse("betting:parlay_add"), {"match_id": m1.pk, "selection": "HOME_WIN"})
        client.post(reverse("betting:parlay_add"), {"match_id": m2.pk, "selection": "DRAW"})

        client.post(reverse("betting:parlay_clear"))

        assert len(_slip(client)) == 0


# ── Parlay slip partial ───────────────────────────────────────────────────────

class TestParlaySlipPartialView:
    def test_returns_200_for_authenticated_user(self, client):
        _login(client)
        resp = client.get(reverse("betting:parlay_slip"))
        assert resp.status_code == 200

    def test_requires_authentication(self, client):
        resp = client.get(reverse("betting:parlay_slip"))
        assert resp.status_code == 302


# ── Place parlay ──────────────────────────────────────────────────────────────

class TestPlaceParlayView:
    def _setup_two_leg_slip(self, client, user):
        """Add two valid legs to the session and return (match1, match2, odds1, odds2)."""
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        o1 = OddsFactory(match=m1, home_win="2.00", draw="3.00", away_win="4.00")
        o2 = OddsFactory(match=m2, home_win="3.00", draw="3.50", away_win="2.50")

        client.post(reverse("betting:parlay_add"), {"match_id": m1.pk, "selection": "HOME_WIN"})
        client.post(reverse("betting:parlay_add"), {"match_id": m2.pk, "selection": "DRAW"})
        return m1, m2, o1, o2

    def test_places_parlay_deducts_balance_creates_records(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="100.00")
        self._setup_two_leg_slip(client, user)

        resp = client.post(reverse("betting:parlay_place"), {"stake": "10.00"})

        assert resp.status_code == 200
        parlay = Parlay.objects.get(user=user)
        assert parlay.stake == Decimal("10.00")
        assert parlay.status == Parlay.Status.PENDING
        assert parlay.legs.count() == 2
        # combined odds = 2.00 * 3.50 = 7.00
        assert parlay.combined_odds == Decimal("7.00")
        user.balance.refresh_from_db()
        assert user.balance.balance == Decimal("90.00")

    def test_slip_cleared_after_placement(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="100.00")
        self._setup_two_leg_slip(client, user)

        client.post(reverse("betting:parlay_place"), {"stake": "10.00"})

        assert len(_slip(client)) == 0

    def test_insufficient_balance_returns_error(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="5.00")
        self._setup_two_leg_slip(client, user)

        resp = client.post(reverse("betting:parlay_place"), {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"Insufficient balance" in resp.content
        assert not Parlay.objects.filter(user=user).exists()
        user.balance.refresh_from_db()
        assert user.balance.balance == Decimal("5.00")

    def test_too_few_legs_rejected(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="100.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)
        client.post(reverse("betting:parlay_add"), {"match_id": match.pk, "selection": "HOME_WIN"})

        resp = client.post(reverse("betting:parlay_place"), {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"at least" in resp.content
        assert not Parlay.objects.filter(user=user).exists()

    def test_invalid_stake_returns_error(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="100.00")
        self._setup_two_leg_slip(client, user)

        resp = client.post(reverse("betting:parlay_place"), {"stake": "0.10"})  # below min

        assert resp.status_code == 200
        assert not Parlay.objects.filter(user=user).exists()

    def test_match_no_longer_bettable_returns_error(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="100.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=m1)
        OddsFactory(match=m2)

        client.post(reverse("betting:parlay_add"), {"match_id": m1.pk, "selection": "HOME_WIN"})
        client.post(reverse("betting:parlay_add"), {"match_id": m2.pk, "selection": "DRAW"})

        # Mark match as finished after adding to slip
        m1.status = Match.Status.FINISHED
        m1.save()

        resp = client.post(reverse("betting:parlay_place"), {"stake": "10.00"})

        assert resp.status_code == 200
        assert b"no longer accepting bets" in resp.content
        assert not Parlay.objects.filter(user=user).exists()

    def test_payout_capped_at_max(self, client):
        user = _login(client)
        UserBalanceFactory(user=user, balance="1000.00")
        m1 = MatchFactory(status=Match.Status.SCHEDULED)
        m2 = MatchFactory(status=Match.Status.SCHEDULED)
        # Very high odds
        OddsFactory(match=m1, home_win="999.99", draw="999.99", away_win="999.99")
        OddsFactory(match=m2, home_win="999.99", draw="999.99", away_win="999.99")

        client.post(reverse("betting:parlay_add"), {"match_id": m1.pk, "selection": "HOME_WIN"})
        client.post(reverse("betting:parlay_add"), {"match_id": m2.pk, "selection": "HOME_WIN"})

        client.post(reverse("betting:parlay_place"), {"stake": "1000.00"})

        parlay = Parlay.objects.get(user=user)
        # Combined odds = 999.99 * 999.99 = 999980.0001, stake = 1000
        # Potential = 999980000.1 > 50000 cap => max_payout stored on record
        assert parlay.max_payout == Decimal("50000.00")

    def test_requires_authentication(self, client):
        resp = client.post(reverse("betting:parlay_place"), {"stake": "10.00"})
        assert resp.status_code == 302
