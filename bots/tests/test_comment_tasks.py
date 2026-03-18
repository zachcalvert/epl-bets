"""Tests for bot comment Celery tasks."""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from bots.models import BotComment
from bots.tasks import (
    generate_bot_comment_task,
    generate_postmatch_comments,
    generate_prematch_comments,
)
from bots.tests.factories import BotUserFactory
from discussions.models import Comment
from matches.models import Match
from matches.tests.factories import MatchFactory

pytestmark = pytest.mark.django_db


class TestGenerateBotCommentTask:
    def _mock_api(self, text="this match is going to be a banger"):
        mock_content = MagicMock()
        mock_content.text = text
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        return mock_response

    def test_creates_comment_on_success(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = self._mock_api()
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                result = generate_bot_comment_task.run(
                    bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH
                )

        assert "posted" in result
        assert Comment.objects.filter(user=bot, match=match).count() == 1

    def test_returns_skipped_when_deduped(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        BotComment.objects.create(
            user=bot, match=match,
            trigger_type=BotComment.TriggerType.PRE_MATCH, error="existing",
        )

        result = generate_bot_comment_task.run(
            bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH
        )

        assert "skipped" in result

    def test_returns_bot_not_found_for_invalid_id(self):
        result = generate_bot_comment_task.run(
            99999, 1, BotComment.TriggerType.PRE_MATCH
        )
        assert result == "bot not found"

    def test_returns_match_not_found_for_invalid_match(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        result = generate_bot_comment_task.run(
            bot.pk, 99999, BotComment.TriggerType.PRE_MATCH
        )
        assert result == "match not found"

    def test_loads_bet_slip_when_provided(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        UserBalanceFactory(user=bot)
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)
        bet = BetSlipFactory(user=bot, match=match)

        with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = self._mock_api()
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                result = generate_bot_comment_task.run(
                    bot.pk, match.pk, BotComment.TriggerType.POST_BET, bet.pk
                )

        assert "posted" in result or "skipped" in result

    def test_handles_missing_bet_slip_gracefully(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)

        with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = self._mock_api()
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                # bet_slip_id 99999 doesn't exist — should not raise
                result = generate_bot_comment_task.run(
                    bot.pk, match.pk, BotComment.TriggerType.POST_BET, 99999
                )

        assert "posted" in result or "skipped" in result


class TestGeneratePrematchComments:
    def test_dispatches_tasks_for_upcoming_matches(self):
        BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timezone.timedelta(hours=2),
        )
        OddsFactory(match=match)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            result = generate_prematch_comments.run()

        assert mock_dispatch.call_count >= 1
        assert "dispatched" in result

    def test_skips_matches_outside_window(self):
        BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        now = timezone.now()
        # Kickoff too far out (>24h)
        MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timezone.timedelta(hours=48),
        )
        # Kickoff too soon (<1h)
        MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timezone.timedelta(minutes=30),
        )

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_prematch_comments.run()

        assert mock_dispatch.call_count == 0

    def test_skips_finished_matches(self):
        BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        now = timezone.now()
        MatchFactory(
            status=Match.Status.FINISHED,
            kickoff=now + timezone.timedelta(hours=2),
        )

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_prematch_comments.run()

        assert mock_dispatch.call_count == 0

    def test_returns_zero_when_no_matches(self):
        result = generate_prematch_comments.run()
        assert "0" in result


class TestGeneratePostmatchComments:
    def test_dispatches_for_bots_with_bets_on_finished_match(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        UserBalanceFactory(user=bot)
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=1, away_score=0,
            updated_at=now - timezone.timedelta(minutes=30),
        )
        BetSlipFactory(user=bot, match=match, status=BetSlip.Status.LOST)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            result = generate_postmatch_comments.run()

        assert mock_dispatch.call_count >= 1
        assert "dispatched" in result

    def test_skips_matches_finished_too_long_ago(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        UserBalanceFactory(user=bot)
        match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
        BetSlipFactory(user=bot, match=match)

        # Backdating updated_at via queryset.update() bypasses auto_now
        from matches.models import Match as MatchModel
        MatchModel.objects.filter(pk=match.pk).update(
            updated_at=timezone.now() - timezone.timedelta(hours=5)
        )

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_postmatch_comments.run()

        assert mock_dispatch.call_count == 0

    def test_skips_bots_who_already_commented(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        UserBalanceFactory(user=bot)
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=1, away_score=0,
            updated_at=now - timezone.timedelta(minutes=30),
        )
        BetSlipFactory(user=bot, match=match)
        # Already commented
        BotComment.objects.create(
            user=bot, match=match,
            trigger_type=BotComment.TriggerType.POST_MATCH, error="existing",
        )

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_postmatch_comments.run()

        # No new dispatch for this bot (may still get color commentary bot if eligible)
        betting_bot_calls = [
            c for c in mock_dispatch.call_args_list
            if c.args[0][0] == bot.pk
        ]
        assert len(betting_bot_calls) == 0

    def test_returns_zero_when_no_finished_matches(self):
        result = generate_postmatch_comments.run()
        assert "0" in result


class TestExecuteBotStrategyCommentHook:
    """Test the post-bet comment hook added to execute_bot_strategy."""

    def test_dispatches_comment_task_after_successful_bet(self):
        from bots.tasks import execute_bot_strategy

        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            # Force the coin flip to always comment
            with patch("bots.tasks.random.random", return_value=0.0):
                execute_bot_strategy.run(bot.pk)

        assert mock_dispatch.call_count >= 1
        call_args = mock_dispatch.call_args_list[0]
        trigger = call_args.kwargs["args"][2] if "args" in call_args.kwargs else call_args[1]["args"][2]
        assert trigger == BotComment.TriggerType.POST_BET

    def test_skips_comment_task_on_coin_flip_miss(self):
        from bots.tasks import execute_bot_strategy

        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        UserBalanceFactory(user=bot, balance="500.00")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match, home_win="1.40", draw="3.80", away_win="5.50")

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            with patch("bots.tasks.random.random", return_value=0.9):
                execute_bot_strategy.run(bot.pk)

        assert mock_dispatch.call_count == 0
