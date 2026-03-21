import pytest

from betting.services import (
    BOARD_TYPES,
    get_leaderboard_entries,
    get_public_identity,
    mask_email,
)
from betting.tests.factories import UserBalanceFactory

pytestmark = pytest.mark.django_db


def test_mask_email_hides_local_part():
    assert mask_email("zach@example.com") == "za**@example.com"


def test_get_public_identity_prefers_display_name():
    balance = UserBalanceFactory()
    user = balance.user
    user.display_name = "Zach"
    user.save()

    assert get_public_identity(user) == "Zach"


def test_get_public_identity_falls_back_to_masked_email():
    balance = UserBalanceFactory()
    user = balance.user

    result = get_public_identity(user)
    assert "@" in result
    assert "*" in result


def test_get_leaderboard_entries_returns_balance_board():
    UserBalanceFactory(balance="5000.00")
    UserBalanceFactory(balance="3000.00")

    entries = get_leaderboard_entries(limit=10, board_type="balance")

    assert len(entries) >= 2
    assert entries[0].balance >= entries[1].balance


def test_board_types_constant():
    assert "balance" in BOARD_TYPES
    assert "profit" in BOARD_TYPES
