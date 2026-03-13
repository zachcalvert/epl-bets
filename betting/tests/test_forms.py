from decimal import Decimal

import pytest

from betting.forms import DisplayNameForm, PlaceBetForm
from betting.models import BetSlip
from users.tests.factories import UserFactory


def test_place_bet_form_valid():
    form = PlaceBetForm(
        data={
            "selection": BetSlip.Selection.HOME_WIN,
            "stake": "25.50",
        }
    )

    assert form.is_valid() is True
    assert form.cleaned_data["stake"] == Decimal("25.50")


def test_place_bet_form_rejects_stake_below_minimum():
    form = PlaceBetForm(
        data={
            "selection": BetSlip.Selection.DRAW,
            "stake": "0.25",
        }
    )

    assert form.is_valid() is False
    assert "Ensure this value is greater than or equal to 0.50." in form.errors["stake"][0]


def test_place_bet_form_rejects_stake_above_maximum():
    form = PlaceBetForm(
        data={
            "selection": BetSlip.Selection.AWAY_WIN,
            "stake": "1000.50",
        }
    )

    assert form.is_valid() is False
    assert "Ensure this value is less than or equal to 1000." in form.errors["stake"][0]


@pytest.mark.django_db
def test_display_name_form_normalizes_blank_to_none():
    user = UserFactory(display_name="Existing")

    form = DisplayNameForm(data={"display_name": "   "}, instance=user)

    assert form.is_valid() is True
    assert form.cleaned_data["display_name"] is None


@pytest.mark.django_db
def test_display_name_form_rejects_case_insensitive_duplicates():
    UserFactory(display_name="TopPunter")
    user = UserFactory()

    form = DisplayNameForm(data={"display_name": " toppunter "}, instance=user)

    assert form.is_valid() is False
    assert form.errors["display_name"] == ["Display name already taken."]
