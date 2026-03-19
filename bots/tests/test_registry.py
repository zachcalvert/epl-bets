"""Tests for the bot strategy registry."""

import pytest

from bots.registry import get_strategy_for_bot
from bots.strategies import (
    FrontrunnerStrategy,
    HomerBotStrategy,
)
from bots.tests.factories import BotUserFactory
from matches.tests.factories import TeamFactory


@pytest.mark.django_db
class TestGetStrategyForBot:
    def test_returns_homer_strategy_for_registered_homer_bot(self):
        team = TeamFactory(tla="ARS")
        user = BotUserFactory(email="arsenal-homer@bots.eplbets.local")

        strategy = get_strategy_for_bot(user)

        assert isinstance(strategy, HomerBotStrategy)
        assert strategy.team_id == team.pk

    def test_homer_strategy_returns_none_when_team_not_in_db(self):
        # No team with TLA "ARS" exists
        user = BotUserFactory(email="arsenal-homer@bots.eplbets.local")

        strategy = get_strategy_for_bot(user)

        assert strategy is None

    def test_returns_static_strategy_for_core_bot(self):
        user = BotUserFactory(email="frontrunner@bots.eplbets.local")

        strategy = get_strategy_for_bot(user)

        assert isinstance(strategy, FrontrunnerStrategy)

    def test_returns_none_for_unrecognised_bot(self):
        user = BotUserFactory(email="unknown@bots.eplbets.local")

        strategy = get_strategy_for_bot(user)

        assert strategy is None
