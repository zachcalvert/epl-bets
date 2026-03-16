"""Tests for bot Celery tasks."""

from unittest.mock import patch

import pytest

from betting.models import BetSlip, Parlay
from betting.tests.factories import OddsFactory, UserBalanceFactory
from bots.tasks import execute_bot_strategy, run_bot_strategies
from bots.tests.factories import BotUserFactory
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestRunBotStrategies:
    def test_dispatches_tasks_for_each_active_bot(self):
        BotUserFactory(is_active=True)
        BotUserFactory(is_active=True)
        BotUserFactory(is_active=False)
        UserFactory()  # Non-bot user

        with patch("bots.tasks.execute_bot_strategy.apply_async") as mock_dispatch:
            result = run_bot_strategies.run()

        assert mock_dispatch.call_count == 2
        assert "2" in result

    def test_dispatches_with_countdown_delay(self):
        BotUserFactory(is_active=True)

        with patch("bots.tasks.execute_bot_strategy.apply_async") as mock_dispatch:
            run_bot_strategies.run()

        call_kwargs = mock_dispatch.call_args.kwargs
        assert "countdown" in call_kwargs
        assert 60 <= call_kwargs["countdown"] <= 600

    def test_returns_early_when_no_bots(self):
        UserFactory()  # Non-bot only

        with patch("bots.tasks.execute_bot_strategy.apply_async") as mock_dispatch:
            result = run_bot_strategies.run()

        assert mock_dispatch.call_count == 0
        assert "0" in result


class TestExecuteBotStrategy:
    def test_places_bets_for_registered_bot(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        # Odds with a clear favorite (1.40 < 1.80 threshold)
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        result = execute_bot_strategy.run(bot.pk)

        assert BetSlip.objects.filter(user=bot).count() >= 1
        assert "1 bets" in result

    def test_returns_early_for_nonexistent_user(self):
        result = execute_bot_strategy.run(99999)

        assert result == "bot not found"

    def test_returns_early_for_non_bot_user(self):
        user = UserFactory()

        result = execute_bot_strategy.run(user.pk)

        assert result == "bot not found"

    def test_returns_early_for_unregistered_bot_email(self):
        bot = BotUserFactory(email="unknown@bots.eplbets.local")
        UserBalanceFactory(user=bot)

        result = execute_bot_strategy.run(bot.pk)

        assert result == "no strategy"

    def test_returns_early_when_no_matches_available(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot)
        # No bettable matches
        MatchFactory(status=Match.Status.FINISHED)

        result = execute_bot_strategy.run(bot.pk)

        assert result == "no matches"

    def test_returns_early_when_no_odds(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot)
        MatchFactory(status=Match.Status.SCHEDULED)
        # Match exists but no odds

        result = execute_bot_strategy.run(bot.pk)

        assert result == "no odds"

    def test_triggers_topup_when_balance_is_low(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="10.00")
        # No bettable matches so task exits early, but topup should have run
        MatchFactory(status=Match.Status.FINISHED)

        with patch("bots.tasks.maybe_topup_bot") as mock_topup:
            execute_bot_strategy.run(bot.pk)

        mock_topup.assert_called_once_with(bot)

    def test_returns_no_balance_when_balance_missing(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        # No UserBalance created
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        result = execute_bot_strategy.run(bot.pk)

        assert result == "no balance"

    def test_value_hunter_bot_uses_full_odds(self):
        bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        # Two bookmakers with a large spread on home_win (> 0.30)
        OddsFactory(match=match, bookmaker="A", home_win="1.50", draw="3.20", away_win="5.00")
        OddsFactory(match=match, bookmaker="B", home_win="2.00", draw="3.30", away_win="5.10")

        result = execute_bot_strategy.run(bot.pk)

        assert "Value Victor" in result or "bets" in result

    def test_parlay_bot_places_parlay(self):
        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")

        # Create enough matches with odds in ParlayStrategy value range (1.40-2.50)
        matches = [MatchFactory(status=Match.Status.SCHEDULED) for _ in range(5)]
        for m in matches:
            OddsFactory(match=m, home_win="1.80", draw="3.20", away_win="4.50")

        result = execute_bot_strategy.run(bot.pk)

        assert "1 parlays" in result
        assert Parlay.objects.filter(user=bot).count() >= 1
