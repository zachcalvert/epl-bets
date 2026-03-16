"""Tests for the bot strategy registry."""

from decimal import Decimal

import pytest

from bots.models import HomerBotConfig
from bots.registry import get_strategy_for_bot
from bots.strategies import (
    FrontrunnerStrategy,
    HomerBotStrategy,
)
from bots.tests.factories import BotUserFactory
from matches.tests.factories import TeamFactory


@pytest.mark.django_db
class TestGetStrategyForBot:
    def test_returns_homer_strategy_for_user_with_config(self):
        team = TeamFactory()
        user = BotUserFactory()
        HomerBotConfig.objects.create(user=user, team=team)

        strategy = get_strategy_for_bot(user)

        assert isinstance(strategy, HomerBotStrategy)
        assert strategy.team_id == team.pk

    def test_homer_strategy_uses_configured_threshold(self):
        team = TeamFactory()
        user = BotUserFactory()
        HomerBotConfig.objects.create(
            user=user,
            team=team,
            draw_underdog_threshold=Decimal("4.00"),
        )

        strategy = get_strategy_for_bot(user)

        assert strategy.draw_underdog_threshold == Decimal("4.00")

    def test_returns_static_strategy_for_non_homer_bot(self):
        user = BotUserFactory(email="frontrunner@bots.eplbets.local")

        strategy = get_strategy_for_bot(user)

        assert isinstance(strategy, FrontrunnerStrategy)

    def test_returns_none_for_unrecognised_bot(self):
        user = BotUserFactory(email="unknown@bots.eplbets.local")

        strategy = get_strategy_for_bot(user)

        assert strategy is None

    def test_homer_config_takes_priority_over_static_map(self):
        """A user whose email is in the static map but also has a HomerBotConfig
        should get the Homer strategy — config wins."""
        team = TeamFactory()
        user = BotUserFactory(email="frontrunner@bots.eplbets.local")
        HomerBotConfig.objects.create(user=user, team=team)

        strategy = get_strategy_for_bot(user)

        assert isinstance(strategy, HomerBotStrategy)
