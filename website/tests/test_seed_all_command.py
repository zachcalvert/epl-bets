"""Smoke tests for the seed_all master seed command."""

from unittest.mock import patch

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


PATCH_TARGET = "website.management.commands.seed_all.call_command"


def test_seed_all_calls_all_sub_commands(capsys):
    with patch(PATCH_TARGET) as mock_call:
        call_command("seed_all")

    called_commands = [c.args[0] for c in mock_call.call_args_list]
    assert called_commands == [
        "seed_epl",
        "seed_challenge_templates",
        "seed_badges",
        "seed_bots",
        "backfill_stats",
    ]


def test_seed_all_skips_epl_when_flag_set(capsys):
    with patch(PATCH_TARGET) as mock_call:
        call_command("seed_all", skip_epl=True)

    called_commands = [c.args[0] for c in mock_call.call_args_list]
    assert "seed_epl" not in called_commands
    assert "seed_bots" in called_commands


def test_seed_all_forwards_offline_flag_to_seed_epl():
    with patch(PATCH_TARGET) as mock_call:
        call_command("seed_all", offline=True)

    seed_epl_call = next(c for c in mock_call.call_args_list if c.args[0] == "seed_epl")
    assert seed_epl_call.kwargs.get("offline") is True


def test_seed_all_forwards_skip_odds_flag_to_seed_epl():
    with patch(PATCH_TARGET) as mock_call:
        call_command("seed_all", skip_odds=True)

    seed_epl_call = next(c for c in mock_call.call_args_list if c.args[0] == "seed_epl")
    assert seed_epl_call.kwargs.get("skip_odds") is True


def test_seed_all_outputs_completion_message(capsys):
    with patch(PATCH_TARGET):
        call_command("seed_all")

    assert "All seed commands complete." in capsys.readouterr().out
