from decimal import Decimal

import pytest

from betting.forms import PlaceBetForm
from betting.models import BetSlip


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
            "stake": "500.50",
        }
    )

    assert form.is_valid() is False
    assert "Ensure this value is less than or equal to 500." in form.errors["stake"][0]
