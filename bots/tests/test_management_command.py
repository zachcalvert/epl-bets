"""Tests for the seed_bots management command."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from betting.models import UserBalance, UserStats
from bots.registry import BOT_PROFILES

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_seed_bots_creates_all_bot_accounts(capsys):
    call_command("seed_bots")

    assert User.objects.filter(is_bot=True).count() == len(BOT_PROFILES)


def test_seed_bots_sets_correct_display_names():
    call_command("seed_bots")

    for profile in BOT_PROFILES:
        user = User.objects.get(email=profile["email"])
        assert user.display_name == profile["display_name"]


def test_seed_bots_marks_accounts_as_bots():
    call_command("seed_bots")

    for profile in BOT_PROFILES:
        user = User.objects.get(email=profile["email"])
        assert user.is_bot is True
        assert user.is_active is True


def test_seed_bots_sets_unusable_password():
    call_command("seed_bots")

    for profile in BOT_PROFILES:
        user = User.objects.get(email=profile["email"])
        assert not user.has_usable_password()


def test_seed_bots_creates_balance_and_stats():
    call_command("seed_bots")

    for profile in BOT_PROFILES:
        user = User.objects.get(email=profile["email"])
        assert UserBalance.objects.filter(user=user).exists()
        assert UserStats.objects.filter(user=user).exists()


def test_seed_bots_is_idempotent(capsys):
    call_command("seed_bots")
    call_command("seed_bots")

    # Should not create duplicates
    assert User.objects.filter(is_bot=True).count() == len(BOT_PROFILES)
    assert UserBalance.objects.filter(user__is_bot=True).count() == len(BOT_PROFILES)


def test_seed_bots_output_reports_created(capsys):
    call_command("seed_bots")
    output = capsys.readouterr().out

    assert "Created" in output
    assert f"{len(BOT_PROFILES)} created" in output


def test_seed_bots_output_reports_updated_on_rerun(capsys):
    call_command("seed_bots")
    call_command("seed_bots")
    output = capsys.readouterr().out

    assert f"{len(BOT_PROFILES)} updated" in output
