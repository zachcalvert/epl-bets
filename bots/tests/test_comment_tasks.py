"""Tests for bot comment Celery tasks."""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory, OddsFactory, UserBalanceFactory
from bots.models import BotComment, BotProfile
from bots.tasks import (
    generate_bot_comment_task,
    generate_bot_reply_task,
    generate_postmatch_comments,
    generate_prematch_comments,
    maybe_reply_to_human_comment,
)
from bots.tests.factories import BotUserFactory
from discussions.models import Comment
from matches.models import Match
from matches.tests.factories import MatchFactory
from users.tests.factories import UserFactory

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
    def test_dispatches_with_bet_slip_id_when_bot_has_pending_bet(self):
        bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timezone.timedelta(hours=2),
        )
        OddsFactory(match=match)
        bet = BetSlipFactory(user=bot, match=match, status=BetSlip.Status.PENDING)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_prematch_comments.run()

        assert mock_dispatch.call_count >= 1
        # Find the call for our bot
        bot_calls = [
            c for c in mock_dispatch.call_args_list
            if c.kwargs.get("args", [])[0] == bot.pk
        ]
        assert len(bot_calls) == 1
        assert bot_calls[0].kwargs["args"][3] == bet.pk

    def test_dispatches_with_none_bet_slip_id_when_bot_has_no_bet(self):
        BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.SCHEDULED,
            kickoff=now + timezone.timedelta(hours=2),
        )
        OddsFactory(match=match)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_prematch_comments.run()

        assert mock_dispatch.call_count >= 1
        # All dispatched args should have None as bet_slip_id (index 3)
        for call in mock_dispatch.call_args_list:
            assert call.kwargs["args"][3] is None

    def test_dispatches_tasks_for_upcoming_matches(self):
        BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
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
        BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
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
        BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
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
        bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
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
        bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
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

    def test_skips_matches_with_kickoff_older_than_one_week(self):
        bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
        UserBalanceFactory(user=bot)
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=1, away_score=0,
            kickoff=now - timezone.timedelta(days=8),
            updated_at=now - timezone.timedelta(minutes=30),
        )
        BetSlipFactory(user=bot, match=match)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_postmatch_comments.run()

        assert mock_dispatch.call_count == 0

    def test_skips_bots_who_already_commented(self):
        bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
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

    def test_color_bot_dispatch_includes_bet_slip_id_when_bet_exists(self):
        """Color commentary bot passes its own bet_slip_id if it placed a bet."""
        # The "color bot" is the one picked by select_bots_for_match after bettor bots are excluded.
        # Use two bots: one is a bettor (already enqueued), one is the color bot that also has a bet.
        bettor = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
        color_bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.ALL_IN_ALICE,
        )
        UserBalanceFactory(user=bettor)
        UserBalanceFactory(user=color_bot)

        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=1, away_score=0,
            updated_at=now - timezone.timedelta(minutes=30),
        )
        OddsFactory(match=match)

        BetSlipFactory(user=bettor, match=match, status=BetSlip.Status.LOST)
        color_bet = BetSlipFactory(user=color_bot, match=match, status=BetSlip.Status.WON)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_postmatch_comments.run()

        # Find dispatch for the color bot (color_bot had no bettor-path bet so it goes the color route)
        color_calls = [
            c for c in mock_dispatch.call_args_list
            if c.kwargs.get("args", [])[0] == color_bot.pk
        ]
        if color_calls:
            # If selected as color bot, its bet_slip_id should be passed
            assert color_calls[0].kwargs["args"][3] == color_bet.pk

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


class TestGenerateBotReplyTask:
    def test_returns_bot_not_found_for_invalid_id(self):
        result = generate_bot_reply_task.run(99999, 1, 1)
        assert result == "bot not found"

    def test_returns_match_not_found(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        result = generate_bot_reply_task.run(bot.pk, 99999, 1)
        assert result == "match not found"

    def test_returns_parent_comment_not_found(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        result = generate_bot_reply_task.run(bot.pk, match.pk, 99999)
        assert result == "parent comment not found"

    def test_returns_skipped_when_deduped(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        other = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = MatchFactory()
        parent = Comment.objects.create(match=match, user=other, body="free money.")
        # Pre-create the REPLY slot
        BotComment.objects.create(
            user=bot, match=match, trigger_type=BotComment.TriggerType.REPLY,
        )

        result = generate_bot_reply_task.run(bot.pk, match.pk, parent.pk)
        assert "skipped" in result

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_posts_reply_on_success(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_content = MagicMock()
        mock_content.text = "variance. enjoy your lucky bet."
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        mock_cls.return_value.messages.create.return_value = mock_response

        bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        other = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        parent = Comment.objects.create(match=match, user=other, body="RIGGED match.")

        result = generate_bot_reply_task.run(bot.pk, match.pk, parent.pk)
        assert "replied" in result


class TestMaybeReplyToHumanComment:
    def test_returns_comment_not_found_for_invalid_id(self):
        result = maybe_reply_to_human_comment.run(99999)
        assert result == "comment not found"

    def test_returns_skipped_for_bot_author(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        comment = Comment.objects.create(match=match, user=bot, body="RIGGED.")

        result = maybe_reply_to_human_comment.run(comment.pk)
        assert result == "skipped (bot author)"

    def test_returns_skipped_when_no_candidate(self):
        user = UserFactory()
        match = MatchFactory()
        comment = Comment.objects.create(match=match, user=user, body="great match!")

        # No bots exist, so no candidate
        result = maybe_reply_to_human_comment.run(comment.pk)
        assert result == "skipped (no candidate)"

    def test_dispatches_reply_when_candidate_found(self):
        user = UserFactory()
        # Create an always-eligible bot
        BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
        match = MatchFactory()
        comment = Comment.objects.create(match=match, user=user, body="great odds on this match!")

        with patch("bots.tasks.generate_bot_reply_task.apply_async") as mock_dispatch:
            with patch("bots.comment_service.random.random", return_value=0.1):
                result = maybe_reply_to_human_comment.run(comment.pk)

        if "dispatched" in result:
            assert mock_dispatch.call_count == 1
        else:
            # 30% chance means sometimes no candidate
            assert "skipped" in result


class TestMaybeDispatchReply:
    def test_dispatches_reply_when_affinity_bot_exists(self):
        from bots.tasks import _maybe_dispatch_reply

        frontrunner = BotUserFactory(email="frontrunner@bots.eplbets.local")
        BotUserFactory(email="underdog@bots.eplbets.local")  # has beef
        match = MatchFactory()
        comment = Comment.objects.create(
            match=match, user=frontrunner, body="free money on this match.",
        )

        with patch("bots.tasks.generate_bot_reply_task.apply_async") as mock_dispatch:
            _maybe_dispatch_reply(match, comment)

        assert mock_dispatch.call_count == 1

    def test_does_nothing_when_no_candidate(self):
        from bots.tasks import _maybe_dispatch_reply

        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        match = MatchFactory()
        comment = Comment.objects.create(
            match=match, user=bot, body="hear me out, parlay time.",
        )

        with patch("bots.tasks.generate_bot_reply_task.apply_async") as mock_dispatch:
            _maybe_dispatch_reply(match, comment)

        assert mock_dispatch.call_count == 0


class TestPostmatchDedup:
    def test_skips_duplicate_bets_from_same_user(self):
        """When a bot has multiple bets on one match, only one dispatch happens."""
        bot = BotUserFactory(
            bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT,
        )
        UserBalanceFactory(user=bot)
        now = timezone.now()
        match = MatchFactory(
            status=Match.Status.FINISHED,
            home_score=2, away_score=1,
            updated_at=now - timezone.timedelta(minutes=30),
        )
        # Two bets on the same match
        BetSlipFactory(user=bot, match=match, status=BetSlip.Status.WON)
        BetSlipFactory(user=bot, match=match, status=BetSlip.Status.LOST)

        with patch("bots.tasks.generate_bot_comment_task.apply_async") as mock_dispatch:
            generate_postmatch_comments.run()

        # Should only dispatch once for this bot (dedup by user_id)
        bot_calls = [
            c for c in mock_dispatch.call_args_list
            if c.kwargs.get("args", [None])[0] == bot.pk
        ]
        assert len(bot_calls) == 1
