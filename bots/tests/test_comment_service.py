"""Tests for bots.comment_service."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from betting.models import BetSlip
from betting.tests.factories import BetSlipFactory, OddsFactory
from bots.comment_service import (
    _filter_comment,
    _homer_team_mentioned,
    _is_bot_relevant,
    generate_bot_comment,
    select_bots_for_match,
    select_reply_bot,
)
from bots.models import BotComment
from bots.tests.factories import BotUserFactory
from discussions.models import Comment
from matches.tests.factories import MatchFactory, TeamFactory

pytestmark = pytest.mark.django_db

FRONTRUNNER = "frontrunner@bots.eplbets.local"
PARLAY_PETE = "parlaypete@bots.eplbets.local"
VALID_COMMENT = "Arsenal look the clear favourite here, backing the home win."


def make_api_response(text):
    """Build a minimal mock Anthropic API response."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# ── generate_bot_comment ──────────────────────────────────────────────────────


class TestGenerateBotComment:
    def test_returns_none_when_already_commented(self):
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory()
        BotComment.objects.create(
            user=bot, match=match, trigger_type=BotComment.TriggerType.PRE_MATCH
        )

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None

    def test_returns_none_when_no_persona_prompt(self):
        bot = BotUserFactory(email="ghost@bots.eplbets.local")
        match = MatchFactory()

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None

    def test_returns_none_and_creates_error_record_when_no_api_key(self, settings):
        settings.ANTHROPIC_API_KEY = ""
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory()

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        assert BotComment.objects.filter(
            user=bot, match=match, error="ANTHROPIC_API_KEY not configured"
        ).exists()

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_returns_none_when_api_call_raises(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.side_effect = Exception("network error")
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory()

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        assert BotComment.objects.filter(
            user=bot, match=match, error="API call failed"
        ).exists()

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_returns_none_and_flags_filtered_when_comment_rejected(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.return_value = make_api_response("short")
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory()

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        assert BotComment.objects.filter(user=bot, match=match, filtered=True).exists()

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_posts_comment_and_creates_bot_comment_record(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.return_value = make_api_response(VALID_COMMENT)
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory()

        comment = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert comment is not None
        assert comment.body == VALID_COMMENT
        assert BotComment.objects.filter(user=bot, match=match, comment=comment).exists()

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_post_bet_trigger_includes_slip_context(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.return_value = make_api_response(VALID_COMMENT)
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory()
        bet_slip = BetSlipFactory(user=bot, match=match)

        comment = generate_bot_comment(
            bot, match, BotComment.TriggerType.POST_BET, bet_slip
        )

        assert comment is not None
        # The user prompt passed to the API should mention the bet
        call_kwargs = mock_cls.return_value.messages.create.call_args.kwargs
        assert "Your bet" in call_kwargs["messages"][0]["content"]

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_post_match_trigger_with_won_slip(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.return_value = make_api_response(VALID_COMMENT)
        bot = BotUserFactory(email=FRONTRUNNER)
        match = MatchFactory(home_score=2, away_score=1)
        bet_slip = BetSlipFactory(
            user=bot, match=match,
            status=BetSlip.Status.WON, payout="21.00",
        )

        comment = generate_bot_comment(
            bot, match, BotComment.TriggerType.POST_MATCH, bet_slip
        )

        assert comment is not None
        call_kwargs = mock_cls.return_value.messages.create.call_args.kwargs
        assert "WON" in call_kwargs["messages"][0]["content"]


# ── select_bots_for_match ─────────────────────────────────────────────────────


class TestSelectBotsForMatch:
    def test_returns_empty_when_no_bots_exist(self):
        match = MatchFactory()

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)

        assert result == []

    def test_excludes_bots_that_already_commented(self):
        bot = BotUserFactory(email=PARLAY_PETE)
        match = MatchFactory()
        BotComment.objects.create(
            user=bot, match=match, trigger_type=BotComment.TriggerType.PRE_MATCH
        )

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)

        assert result == []

    def test_excludes_bots_without_persona_prompt(self):
        BotUserFactory(email="orphan@bots.eplbets.local")
        match = MatchFactory()

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)

        assert result == []

    def test_returns_at_most_max_bots(self):
        for email in (PARLAY_PETE, "chaoscharlie@bots.eplbets.local", "allinalice@bots.eplbets.local"):
            BotUserFactory(email=email)
        match = MatchFactory()

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH, max_bots=2)

        assert len(result) <= 2

    def test_returns_single_bot_when_max_bots_1(self):
        BotUserFactory(email=PARLAY_PETE)
        match = MatchFactory()

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH, max_bots=1)

        assert len(result) == 1


# ── _is_bot_relevant ──────────────────────────────────────────────────────────


class TestIsBotRelevant:
    def test_frontrunner_relevant_with_clear_favourite(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = MatchFactory()
        odds = {"home_win": Decimal("1.40"), "draw": Decimal("3.80"), "away_win": Decimal("5.50")}
        assert _is_bot_relevant(bot, match, odds) is True

    def test_frontrunner_not_relevant_when_odds_too_close(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = MatchFactory()
        odds = {"home_win": Decimal("2.20"), "draw": Decimal("3.20"), "away_win": Decimal("2.80")}
        assert _is_bot_relevant(bot, match, odds) is False

    def test_frontrunner_not_relevant_when_no_odds(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is False

    def test_underdog_relevant_with_big_outsider(self):
        bot = BotUserFactory(email="underdog@bots.eplbets.local")
        match = MatchFactory()
        odds = {"home_win": Decimal("1.50"), "draw": Decimal("3.50"), "away_win": Decimal("5.00")}
        assert _is_bot_relevant(bot, match, odds) is True

    def test_underdog_not_relevant_when_no_odds(self):
        bot = BotUserFactory(email="underdog@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is False

    def test_drawdoctor_relevant_in_sweet_spot(self):
        bot = BotUserFactory(email="drawdoctor@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"draw": Decimal("3.20")}) is True

    def test_drawdoctor_not_relevant_outside_range(self):
        bot = BotUserFactory(email="drawdoctor@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"draw": Decimal("4.50")}) is False

    def test_drawdoctor_not_relevant_when_no_draw_odds(self):
        bot = BotUserFactory(email="drawdoctor@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is False

    def test_valuehunter_relevant_with_two_bookmakers(self):
        bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        match = MatchFactory()
        OddsFactory(match=match, bookmaker="BookieA")
        OddsFactory(match=match, bookmaker="BookieB")
        assert _is_bot_relevant(bot, match, {}) is True

    def test_valuehunter_not_relevant_with_one_bookmaker(self):
        bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        match = MatchFactory()
        OddsFactory(match=match)
        assert _is_bot_relevant(bot, match, {}) is False

    def test_always_eligible_bots_return_true(self):
        always_on = [PARLAY_PETE, "chaoscharlie@bots.eplbets.local", "allinalice@bots.eplbets.local"]
        match = MatchFactory()
        for email in always_on:
            bot = BotUserFactory(email=email)
            assert _is_bot_relevant(bot, match, {}) is True

    def test_homer_bot_relevant_when_their_team_is_playing(self):
        team = TeamFactory(tla="ARS")
        bot = BotUserFactory(email="arsenal-homer@bots.eplbets.local")
        match = MatchFactory(home_team=team)

        assert _is_bot_relevant(bot, match, {}) is True

    def test_homer_bot_relevant_when_their_team_is_away(self):
        team = TeamFactory(tla="ARS")
        bot = BotUserFactory(email="arsenal-homer@bots.eplbets.local")
        match = MatchFactory(away_team=team)

        assert _is_bot_relevant(bot, match, {}) is True

    def test_homer_bot_not_relevant_when_team_not_in_match(self):
        TeamFactory(tla="CHE")
        bot = BotUserFactory(email="chelsea-homer@bots.eplbets.local")
        match = MatchFactory()  # random teams, not Chelsea

        assert _is_bot_relevant(bot, match, {}) is False

    def test_unknown_bot_returns_false(self):
        bot = BotUserFactory(email="mystery@bots.eplbets.local")
        match = MatchFactory()

        assert _is_bot_relevant(bot, match, {}) is False


# ── _filter_comment ───────────────────────────────────────────────────────────


class TestFilterComment:
    def test_rejects_too_short(self):
        match = MatchFactory()
        ok, reason = _filter_comment("short", match)
        assert ok is False
        assert reason == "too_short"

    def test_rejects_too_long(self):
        match = MatchFactory()
        ok, reason = _filter_comment("x" * 501, match)
        assert ok is False
        assert reason == "too_long"

    def test_rejects_profanity(self):
        match = MatchFactory()
        text = f"This match is absolute shit, {match.home_team.name} are fraud."
        ok, reason = _filter_comment(text, match)
        assert ok is False
        assert reason.startswith("profanity:")

    def test_rejects_irrelevant_content(self):
        match = MatchFactory()
        ok, reason = _filter_comment(
            "A perfectly ordinary and unrelated day here indeed.", match
        )
        assert ok is False
        assert reason == "irrelevant"

    def test_accepts_comment_mentioning_team_name(self):
        match = MatchFactory()
        text = f"{match.home_team.name} look great for this one."
        ok, reason = _filter_comment(text, match)
        assert ok is True
        assert reason == ""

    def test_accepts_comment_with_football_keyword(self):
        match = MatchFactory()
        ok, reason = _filter_comment(
            "Great odds on this one, backing the underdog here!", match
        )
        assert ok is True
        assert reason == ""

    def test_accepts_comment_mentioning_away_team(self):
        match = MatchFactory()
        text = f"Can {match.away_team.name} pull off the upset away from home?"
        ok, reason = _filter_comment(text, match)
        assert ok is True

    def test_accepts_comment_mentioning_tla(self):
        match = MatchFactory()
        tla = match.home_team.tla
        ok, reason = _filter_comment(
            f"{tla} should win this match comfortably.", match
        )
        assert ok is True


# ── select_reply_bot ─────────────────────────────────────────────────────────


class TestSelectReplyBot:
    def test_returns_none_when_reply_cap_reached(self):
        match = MatchFactory()
        comment = Comment.objects.create(
            match=match,
            user=BotUserFactory(email=FRONTRUNNER),
            body="free money.",
        )
        # Fill up 4 reply slots
        for i in range(4):
            bot = BotUserFactory(email=f"filler{i}@bots.eplbets.local")
            BotComment.objects.create(
                user=bot, match=match, trigger_type=BotComment.TriggerType.REPLY,
            )

        result = select_reply_bot(match, comment)
        assert result is None

    def test_returns_affinity_bot_for_bot_comment(self):
        # ChalkEater posts, heartbreak_fc has beef with them
        frontrunner = BotUserFactory(email=FRONTRUNNER)
        underdog = BotUserFactory(email="underdog@bots.eplbets.local")
        match = MatchFactory()
        comment = Comment.objects.create(
            match=match, user=frontrunner, body="free money, easy match.",
        )

        result = select_reply_bot(match, comment)
        assert result is not None
        assert result.pk == underdog.pk

    def test_does_not_reply_to_self(self):
        bot = BotUserFactory(email=PARLAY_PETE)
        match = MatchFactory()
        comment = Comment.objects.create(
            match=match, user=bot, body="hear me out, 5 leg parlay this time.",
        )

        # Only parlay_graveyard exists, so no one can reply
        result = select_reply_bot(match, comment)
        assert result is None

    def test_skips_bot_that_already_replied(self):
        frontrunner = BotUserFactory(email=FRONTRUNNER)
        underdog = BotUserFactory(email="underdog@bots.eplbets.local")
        match = MatchFactory()
        comment = Comment.objects.create(
            match=match, user=frontrunner, body="free money.",
        )
        # underdog already used REPLY slot for this match
        BotComment.objects.create(
            user=underdog, match=match, trigger_type=BotComment.TriggerType.REPLY,
        )

        result = select_reply_bot(match, comment)
        assert result is None

    def test_homer_bot_replies_when_team_mentioned(self):
        team = TeamFactory(tla="ARS", name="Arsenal FC")
        homer = BotUserFactory(email="arsenal-homer@bots.eplbets.local")
        other_bot = BotUserFactory(email=PARLAY_PETE)
        match = MatchFactory(home_team=team)
        comment = Comment.objects.create(
            match=match, user=other_bot, body="Arsenal are going to bottle this.",
        )

        result = select_reply_bot(match, comment)
        assert result is not None
        assert result.pk == homer.pk


# ── _homer_team_mentioned ────────────────────────────────────────────────────


class TestHomerTeamMentioned:
    def test_returns_true_when_team_name_in_text(self):
        TeamFactory(tla="ARS", name="Arsenal FC")
        bot = BotUserFactory(email="arsenal-homer@bots.eplbets.local")

        assert _homer_team_mentioned(bot, "Arsenal FC are looking great") is True

    def test_returns_true_when_tla_in_text(self):
        TeamFactory(tla="LIV", name="Liverpool FC")
        bot = BotUserFactory(email="liverpool-homer@bots.eplbets.local")

        assert _homer_team_mentioned(bot, "LIV should win this") is True

    def test_returns_false_when_no_mention(self):
        TeamFactory(tla="CHE", name="Chelsea FC")
        bot = BotUserFactory(email="chelsea-homer@bots.eplbets.local")

        assert _homer_team_mentioned(bot, "Great match ahead") is False

    def test_returns_false_for_non_homer_bot(self):
        bot = BotUserFactory(email=FRONTRUNNER)

        assert _homer_team_mentioned(bot, "anything") is False


# ── generate_bot_comment with REPLY trigger ──────────────────────────────────


class TestGenerateBotReply:
    @patch("bots.comment_service.anthropic.Anthropic")
    def test_reply_creates_comment_with_parent(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.return_value = make_api_response(
            "variance. enjoy your lucky bet while it lasts."
        )
        replying_bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        other_bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        parent = Comment.objects.create(
            match=match, user=other_bot, body="I KNEW IT. RIGGED.",
        )

        reply = generate_bot_comment(
            replying_bot, match, BotComment.TriggerType.REPLY,
            parent_comment=parent,
        )

        assert reply is not None
        assert reply.parent == parent
        assert reply.body == "variance. enjoy your lucky bet while it lasts."

    @patch("bots.comment_service.anthropic.Anthropic")
    def test_reply_prompt_includes_parent_text(self, mock_cls, settings):
        settings.ANTHROPIC_API_KEY = "test-key"
        mock_cls.return_value.messages.create.return_value = make_api_response(
            "correct process, terrible result."
        )
        replying_bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        other_bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        parent = Comment.objects.create(
            match=match, user=other_bot, body="RIGGED I tell you.",
        )

        generate_bot_comment(
            replying_bot, match, BotComment.TriggerType.REPLY,
            parent_comment=parent,
        )

        call_kwargs = mock_cls.return_value.messages.create.call_args.kwargs
        user_prompt = call_kwargs["messages"][0]["content"]
        assert "RIGGED I tell you." in user_prompt
        assert other_bot.display_name in user_prompt
