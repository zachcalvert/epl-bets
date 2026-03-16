from decimal import Decimal
from unittest.mock import patch

import pytest
from django.urls import reverse

from betting.models import Bailout, Bankruptcy, BetSlip, UserBalance
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory
from website.transparency import get_events, match_scope, page_scope, record_event

pytestmark = pytest.mark.django_db


def test_odds_board_view_lists_upcoming_matches_with_best_odds(client):
    match = MatchFactory(status=Match.Status.SCHEDULED)
    MatchFactory(status=Match.Status.FINISHED)
    OddsFactory(match=match, bookmaker="A", home_win="2.40", draw="3.40", away_win="3.30")
    OddsFactory(match=match, bookmaker="B", home_win="2.10", draw="3.10", away_win="3.80")

    response = client.get(reverse("betting:odds"))

    matches = list(response.context["matches"])
    assert response.status_code == 200
    assert matches == [match]
    assert matches[0].best_home_odds == Decimal("2.10")
    assert matches[0].best_draw_odds == Decimal("3.10")
    assert matches[0].best_away_odds == Decimal("3.30")


def test_odds_board_view_excludes_upcoming_matches_without_odds(client):
    match_with_odds = MatchFactory(status=Match.Status.SCHEDULED)
    MatchFactory(status=Match.Status.SCHEDULED)
    OddsFactory(match=match_with_odds, home_win="2.25", draw="3.20", away_win="3.60")

    response = client.get(reverse("betting:odds"))

    matches = list(response.context["matches"])
    assert response.status_code == 200
    assert matches == [match_with_odds]


def test_odds_board_view_renders_under_the_hood_summary_from_recent_events(client):
    record_event(
        scope=page_scope("odds_board"),
        category="celery",
        source="fetch_odds",
        action="odds_synced",
        summary="Odds sync completed.",
        detail="Created 3 bookmaker rows and updated 4 existing rows.",
        status="success",
    )

    response = client.get(reverse("betting:odds"))

    assert response.status_code == 200
    assert "Under the Hood" in response.content.decode()
    assert "Odds sync completed." in response.content.decode()


def test_odds_board_partial_uses_partial_template(client):
    response = client.get(reverse("betting:odds_partial"))

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/odds_board_body.html"
        for template in response.templates
    )
    assert get_events(page_scope("odds_board"))[0]["source"] == "odds_board_partial"


def test_odds_board_under_the_hood_partial_renders_recent_events(client):
    record_event(
        scope=page_scope("odds_board"),
        category="htmx",
        source="odds_board_partial",
        action="partial_refreshed",
        summary="Odds board refreshed with the latest stored prices.",
        detail="Rendered 8 upcoming matches.",
        status="info",
    )

    response = client.get(
        reverse("betting:odds_under_the_hood"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/odds_board_under_the_hood.html"
        for template in response.templates
    )
    assert "Recent odds-board events" in response.content.decode()
    assert "Odds board refreshed with the latest stored prices." in response.content.decode()


def test_place_bet_redirects_anonymous_user_to_login(client):
    match = MatchFactory()

    response = client.post(reverse("betting:place_bet", args=[match.pk]))

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_place_bet_rejects_non_upcoming_match(client):
    user = UserFactory()
    match = MatchFactory(status=Match.Status.FINISHED)
    client.force_login(user)

    response = client.post(reverse("betting:place_bet", args=[match.pk]), data={})

    assert response.status_code == 200
    assert "no longer accepting bets" in response.content.decode()


def test_place_bet_rerenders_invalid_form(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "0.10"},
    )

    assert response.status_code == 200
    assert response.context["form"].errors["stake"] == [
        "Ensure this value is greater than or equal to 0.50."
    ]


def test_place_bet_returns_error_when_no_odds_available(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    assert response.status_code == 200
    assert "No odds available for this match." in response.content.decode()


def test_place_bet_returns_error_for_insufficient_balance(client):
    user = UserFactory()
    UserBalanceFactory(user=user, balance="5.00")
    match = MatchFactory()
    OddsFactory(match=match, home_win="2.25")
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    assert response.status_code == 200
    assert "Insufficient balance. You have £5.00." in response.content.decode()
    assert BetSlip.objects.count() == 0


def test_place_bet_creates_bet_and_deducts_balance(client):
    user = UserFactory()
    balance = UserBalanceFactory(user=user, balance="100.00")
    match = MatchFactory()
    OddsFactory(match=match, bookmaker="A", home_win="2.50")
    OddsFactory(match=match, bookmaker="B", home_win="2.10")
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    bet = BetSlip.objects.get()
    balance.refresh_from_db()

    assert response.status_code == 200
    assert bet.odds_at_placement == Decimal("2.10")
    assert balance.balance == Decimal("90.00")
    assert "21.00" in response.content.decode()
    assert get_events(match_scope(match.pk))[0]["action"] == "bet_placed"


def test_place_bet_confirmation_includes_oob_sentiment_update(client):
    user = UserFactory()
    UserBalanceFactory(user=user, balance="100.00")
    match = MatchFactory()
    OddsFactory(match=match, home_win="2.10")
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "10.00"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    # The OOB sentiment element must be present so HTMX updates the page in-place
    assert 'id="community-sentiment"' in content
    assert 'hx-swap-oob="true"' in content
    # Sentiment data reflects the just-placed bet
    assert "Community Sentiment" in content
    assert "1 bet" in content
    assert "Home Win" in content


def test_place_bet_auto_creates_balance_when_missing(client):
    user = UserFactory()
    match = MatchFactory()
    OddsFactory(match=match, draw="3.40")
    client.force_login(user)

    client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.DRAW, "stake": "25.00"},
    )

    assert UserBalance.objects.get(user=user).balance == Decimal("975.00")


def test_my_bets_view_calculates_totals_and_default_balance(client):
    user = UserFactory()
    won_bet = BetSlipFactory(user=user, stake="10.00", payout="21.00", status=BetSlip.Status.WON)
    lost_bet = BetSlipFactory(user=user, stake="5.00", payout="0.00", status=BetSlip.Status.LOST)
    client.force_login(user)

    response = client.get(reverse("betting:my_bets"))

    bets = list(response.context["bets"])
    assert response.status_code == 200
    assert bets == [lost_bet, won_bet]
    assert response.context["total_staked"] == Decimal("15.00")
    assert response.context["total_payout"] == Decimal("21.00")
    assert response.context["net_pnl"] == Decimal("6.00")
    assert response.context["current_balance"] == Decimal("1000.00")


def test_quick_bet_form_view_returns_initial_selection(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.get(
        reverse("betting:quick_bet_form", args=[match.pk]),
        data={"selection": BetSlip.Selection.AWAY_WIN, "container": f"quick-bet-{match.pk}"},
    )

    assert response.status_code == 200
    assert response.context["selection"] == BetSlip.Selection.AWAY_WIN
    assert response.context["form"].initial["selection"] == BetSlip.Selection.AWAY_WIN
    assert response.context["container_id"] == f"quick-bet-{match.pk}"


def test_quick_bet_form_view_passes_container_id_to_template(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.get(
        reverse("betting:quick_bet_form", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "container": f"quick-bet-mobile-{match.pk}"},
    )

    assert response.status_code == 200
    assert response.context["container_id"] == f"quick-bet-mobile-{match.pk}"
    assert f'hx-target="#quick-bet-mobile-{match.pk}"' in response.content.decode()


def test_place_bet_from_odds_board_returns_quick_bet_form_on_error(client):
    user = UserFactory()
    match = MatchFactory()
    container_id = f"quick-bet-{match.pk}"
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={
            "selection": BetSlip.Selection.HOME_WIN,
            "stake": "0.10",
            "container_id": container_id,
        },
    )

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/quick_bet_form.html"
        for template in response.templates
    )
    assert response.context["container_id"] == container_id


def test_place_bet_from_odds_board_returns_quick_bet_form_on_no_odds(client):
    user = UserFactory()
    match = MatchFactory()
    container_id = f"quick-bet-{match.pk}"
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={
            "selection": BetSlip.Selection.HOME_WIN,
            "stake": "10.00",
            "container_id": container_id,
        },
    )

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/quick_bet_form.html"
        for template in response.templates
    )
    assert "No odds available for this match." in response.content.decode()
    assert f'hx-target="#{container_id}"' in response.content.decode()


def test_place_bet_from_odds_board_returns_quick_bet_form_on_insufficient_balance(client):
    user = UserFactory()
    UserBalanceFactory(user=user, balance="5.00")
    match = MatchFactory()
    OddsFactory(match=match, home_win="2.25")
    container_id = f"quick-bet-{match.pk}"
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={
            "selection": BetSlip.Selection.HOME_WIN,
            "stake": "10.00",
            "container_id": container_id,
        },
    )

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/quick_bet_form.html"
        for template in response.templates
    )
    assert "Insufficient balance" in response.content.decode()


def test_place_bet_without_container_id_returns_bet_form_on_error(client):
    user = UserFactory()
    match = MatchFactory()
    client.force_login(user)

    response = client.post(
        reverse("betting:place_bet", args=[match.pk]),
        data={"selection": BetSlip.Selection.HOME_WIN, "stake": "0.10"},
    )

    assert response.status_code == 200
    assert any(
        template.name == "betting/partials/bet_form.html"
        for template in response.templates
    )


# --- Bailout view tests ---


def test_bailout_redirects_anonymous_user(client):
    response = client.post(reverse("betting:bailout"))

    assert response.status_code == 302
    assert reverse("website:login") in response.url


def test_bailout_returns_error_when_not_bankrupt(client):
    user = UserFactory()
    UserBalanceFactory(user=user, balance="500.00")
    client.force_login(user)

    response = client.post(reverse("betting:bailout"))

    assert response.status_code == 400
    assert response.json()["error"] == "You are not bankrupt."
    assert Bankruptcy.objects.count() == 0


def test_bailout_returns_error_when_pending_bets_exist(client):
    user = UserFactory()
    UserBalanceFactory(user=user, balance="0.00")
    BetSlipFactory(user=user, status=BetSlip.Status.PENDING)
    client.force_login(user)

    response = client.post(reverse("betting:bailout"))

    assert response.status_code == 400
    assert response.json()["error"] == "You are not bankrupt."


def test_bailout_returns_error_when_no_balance_exists(client):
    user = UserFactory()
    client.force_login(user)

    response = client.post(reverse("betting:bailout"))

    assert response.status_code == 400
    assert response.json()["error"] == "No balance found."


@patch("betting.views.random.randint", return_value=2000)
def test_bailout_creates_records_and_credits_balance(mock_randint, client):
    user = UserFactory()
    balance = UserBalanceFactory(user=user, balance="0.25")
    client.force_login(user)

    response = client.post(reverse("betting:bailout"))

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["amount"] == 2000
    assert data["new_balance"] == "2000.25"

    balance.refresh_from_db()
    assert balance.balance == Decimal("2000.25")

    bankruptcy = Bankruptcy.objects.get(user=user)
    assert bankruptcy.balance_at_bankruptcy == Decimal("0.25")

    bailout = Bailout.objects.get(user=user)
    assert bailout.bankruptcy == bankruptcy
    assert bailout.amount == 2000
