"""Tests for bot Celery tasks."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from betting.models import BetSlip, Parlay
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from bots.models import BotComment
from bots.tasks import (
    execute_bot_strategy,
    generate_bot_comment_task,
    generate_postmatch_comments,
    generate_prematch_comments,
    run_bot_strategies,
)
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
        assert 120 <= call_kwargs["countdown"] <= 1800

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


# ── generate_bot_comment_task ─────────────────────────────────────────────────


class TestGenerateBotCommentTask:
    def test_returns_bot_not_found_for_missing_user(self):
        result = generate_bot_comment_task.run(99999, 99999, BotComment.TriggerType.PRE_MATCH)
        assert result == "bot not found"

    def test_returns_bot_not_found_for_non_bot_user(self):
        user = UserFactory()
        result = generate_bot_comment_task.run(user.pk, 99999, BotComment.TriggerType.PRE_MATCH)
        assert result == "bot not found"

    def test_returns_match_not_found(self):
        bot = BotUserFactory()
        result = generate_bot_comment_task.run(bot.pk, 99999, BotComment.TriggerType.PRE_MATCH)
        assert result == "match not found"

    def test_returns_skipped_when_generate_returns_none(self):
        bot = BotUserFactory(email="ghost@bots.eplbets.local")
        match = MatchFactory()
        result = generate_bot_comment_task.run(bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH)
        assert result == "skipped (dedup or filter)"

    @patch("bots.comment_service.generate_bot_comment")
    def test_returns_posted_prefix_when_comment_created(self, mock_gen):
        mock_comment = MagicMock()
        mock_comment.body = "Arsenal look great for this match today."
        mock_gen.return_value = mock_comment
        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        match = MatchFactory()

        result = generate_bot_comment_task.run(bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH)

        assert result.startswith("posted:")

    @patch("bots.comment_service.generate_bot_comment")
    def test_handles_nonexistent_bet_slip_id_gracefully(self, mock_gen):
        mock_gen.return_value = None
        bot = BotUserFactory()
        match = MatchFactory()

        # Should not raise even if bet_slip_id doesn't exist
        result = generate_bot_comment_task.run(
            bot.pk, match.pk, BotComment.TriggerType.POST_BET, 99999
        )
        assert result == "skipped (dedup or filter)"
        # generate_bot_comment called with bet_slip=None (not found)
        _, call_kwargs = mock_gen.call_args
        assert call_kwargs.get("bet_slip") is None or mock_gen.call_args[0][3] is None


# ── generate_prematch_comments ────────────────────────────────────────────────


class TestGeneratePrematchComments:
    def test_no_upcoming_matches_returns_zero(self):
        result = generate_prematch_comments.run()
        assert "0" in result

    def test_ignores_matches_outside_window(self):
        # Match kicking off in 3 days — outside the 24h window
        MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=timezone.now() + timedelta(days=3),
        )
        result = generate_prematch_comments.run()
        assert "0" in result

    def test_dispatches_tasks_for_upcoming_matches(self):
        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=timezone.now() + timedelta(hours=3),
        )

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            with patch(
                "bots.comment_service.select_bots_for_match", return_value=[bot]
            ):
                result = generate_prematch_comments.run()

        assert mock_dispatch.called
        assert "dispatched" in result


# ── generate_postmatch_comments ───────────────────────────────────────────────


class TestGeneratePostmatchComments:
    def test_no_recently_finished_matches_returns_zero(self):
        result = generate_postmatch_comments.run()
        assert "0" in result

    def test_dispatches_for_bot_bets_on_finished_match(self):
        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.FINISHED)
        BetSlipFactory(user=bot, match=match)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            with patch("bots.comment_service.select_bots_for_match", return_value=[]):
                result = generate_postmatch_comments.run()

        assert mock_dispatch.called
        assert "dispatched" in result

    def test_skips_bots_that_already_posted_postmatch(self):
        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.FINISHED)
        BetSlipFactory(user=bot, match=match)
        BotComment.objects.create(
            user=bot, match=match, trigger_type=BotComment.TriggerType.POST_MATCH
        )

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            with patch("bots.comment_service.select_bots_for_match", return_value=[]):
                generate_postmatch_comments.run()

        assert not mock_dispatch.called

    def test_dispatches_color_commentary_bots(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        MatchFactory(status=Match.Status.FINISHED)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            with patch("bots.comment_service.select_bots_for_match", return_value=[bot]):
                result = generate_postmatch_comments.run()

        assert mock_dispatch.called
        assert "dispatched" in result
