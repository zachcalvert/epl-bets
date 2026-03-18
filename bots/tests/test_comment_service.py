"""Tests for bot comment generation service."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from betting.models import BetSlip
from betting.tests.factories import OddsFactory, UserBalanceFactory
from bots.comment_service import (
    _build_user_prompt,
    _filter_comment,
    _is_bot_relevant,
    generate_bot_comment,
    select_bots_for_match,
)
from bots.models import BotComment
from bots.tests.factories import BotUserFactory
from discussions.models import Comment
from matches.models import Match
from matches.tests.factories import MatchFactory, MatchStatsFactory, TeamFactory

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# _filter_comment
# ---------------------------------------------------------------------------

class TestFilterComment:
    def _make_match(self):
        return MatchFactory(
            home_team=TeamFactory(name="Arsenal", short_name="ARS", tla="ARS"),
            away_team=TeamFactory(name="Chelsea", short_name="CHE", tla="CHE"),
        )

    def test_passes_with_team_name(self):
        match = self._make_match()
        ok, reason = _filter_comment("Arsenal are going to dominate today", match)
        assert ok is True
        assert reason == ""

    def test_passes_with_football_keyword(self):
        match = self._make_match()
        ok, reason = _filter_comment("this match has banger written all over it", match)
        assert ok is True

    def test_passes_with_short_name(self):
        match = self._make_match()
        ok, reason = _filter_comment("ARS to win this one easily", match)
        assert ok is True

    def test_rejects_too_short(self):
        match = self._make_match()
        ok, reason = _filter_comment("hi", match)
        assert ok is False
        assert reason == "too_short"

    def test_rejects_too_long(self):
        match = self._make_match()
        ok, reason = _filter_comment("x" * 501, match)
        assert ok is False
        assert reason == "too_long"

    def test_rejects_profanity(self):
        match = self._make_match()
        ok, reason = _filter_comment("Arsenal are shit at defending", match)
        assert ok is False
        assert "profanity" in reason

    def test_rejects_irrelevant(self):
        match = self._make_match()
        ok, reason = _filter_comment("I really like pizza and ice cream today!", match)
        assert ok is False
        assert reason == "irrelevant"

    def test_profanity_check_is_word_boundary(self):
        # "dick" should not match inside "dickens"
        match = self._make_match()
        ok, _ = _filter_comment("Dickens would have written about this match", match)
        assert ok is True

    def test_exact_500_chars_passes(self):
        match = self._make_match()
        text = ("Arsenal " + "x" * 492)[:500]
        ok, _ = _filter_comment(text, match)
        assert ok is True

    def test_exact_10_chars_passes(self):
        match = self._make_match()
        ok, _ = _filter_comment("Arsenal go", match)
        assert ok is True


# ---------------------------------------------------------------------------
# _is_bot_relevant
# ---------------------------------------------------------------------------

class TestIsBotRelevant:
    def _match_with_odds(self, home_win, draw, away_win, bookmakers=1):
        match = MatchFactory()
        for i in range(bookmakers):
            OddsFactory(match=match, bookmaker=f"bookie{i}", home_win=str(home_win), draw=str(draw), away_win=str(away_win))
        return match

    def test_frontrunner_relevant_with_clear_favorite(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = self._match_with_odds(1.40, 3.50, 5.00)
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("1.40"), "draw": Decimal("3.50"), "away_win": Decimal("5.00")}) is True

    def test_frontrunner_not_relevant_when_no_clear_favorite(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = self._match_with_odds(2.10, 3.20, 2.90)
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("2.10"), "draw": Decimal("3.20"), "away_win": Decimal("2.90")}) is False

    def test_frontrunner_not_relevant_with_no_odds(self):
        bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is False

    def test_underdog_relevant_when_clear_underdog(self):
        bot = BotUserFactory(email="underdog@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("1.50"), "draw": Decimal("3.50"), "away_win": Decimal("5.00")}) is True

    def test_underdog_not_relevant_when_no_clear_underdog(self):
        bot = BotUserFactory(email="underdog@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("1.80"), "draw": Decimal("3.20"), "away_win": Decimal("2.50")}) is False

    def test_draw_doctor_relevant_in_sweet_spot(self):
        bot = BotUserFactory(email="drawdoctor@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("2.10"), "draw": Decimal("3.20"), "away_win": Decimal("2.90")}) is True

    def test_draw_doctor_not_relevant_below_sweet_spot(self):
        bot = BotUserFactory(email="drawdoctor@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("2.10"), "draw": Decimal("2.50"), "away_win": Decimal("2.90")}) is False

    def test_draw_doctor_not_relevant_above_sweet_spot(self):
        bot = BotUserFactory(email="drawdoctor@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {"home_win": Decimal("2.10"), "draw": Decimal("4.00"), "away_win": Decimal("2.90")}) is False

    def test_value_victor_relevant_with_multiple_bookmakers(self):
        bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        match = self._match_with_odds(2.10, 3.20, 2.90, bookmakers=2)
        assert _is_bot_relevant(bot, match, {}) is True

    def test_value_victor_not_relevant_with_single_bookmaker(self):
        bot = BotUserFactory(email="valuehunter@bots.eplbets.local")
        match = self._match_with_odds(2.10, 3.20, 2.90, bookmakers=1)
        assert _is_bot_relevant(bot, match, {}) is False

    def test_parlay_pete_always_relevant(self):
        bot = BotUserFactory(email="parlaypete@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is True

    def test_chaos_charlie_always_relevant(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is True

    def test_all_in_alice_always_relevant(self):
        bot = BotUserFactory(email="allinalice@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is True

    def test_homer_bot_relevant_when_team_is_home(self):
        from bots.models import HomerBotConfig
        team = TeamFactory()
        bot = BotUserFactory(email="homer1@bots.eplbets.local")
        HomerBotConfig.objects.create(user=bot, team=team)
        match = MatchFactory(home_team=team)
        assert _is_bot_relevant(bot, match, {}) is True

    def test_homer_bot_relevant_when_team_is_away(self):
        from bots.models import HomerBotConfig
        team = TeamFactory()
        bot = BotUserFactory(email="homer2@bots.eplbets.local")
        HomerBotConfig.objects.create(user=bot, team=team)
        match = MatchFactory(away_team=team)
        assert _is_bot_relevant(bot, match, {}) is True

    def test_homer_bot_not_relevant_when_team_not_playing(self):
        from bots.models import HomerBotConfig
        team = TeamFactory()
        bot = BotUserFactory(email="homer3@bots.eplbets.local")
        HomerBotConfig.objects.create(user=bot, team=team)
        match = MatchFactory()  # Different teams
        assert _is_bot_relevant(bot, match, {}) is False

    def test_unknown_bot_returns_false(self):
        bot = BotUserFactory(email="unknown@bots.eplbets.local")
        match = MatchFactory()
        assert _is_bot_relevant(bot, match, {}) is False


# ---------------------------------------------------------------------------
# _build_user_prompt
# ---------------------------------------------------------------------------

class TestBuildUserPrompt:
    def test_pre_match_prompt_includes_teams_and_instruction(self):
        match = MatchFactory(
            home_team=TeamFactory(name="Liverpool"),
            away_team=TeamFactory(name="Everton"),
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "Liverpool" in prompt
        assert "Everton" in prompt
        assert "pre-match hype" in prompt

    def test_prompt_includes_odds_when_available(self):
        match = MatchFactory()
        OddsFactory(match=match, home_win="1.50", draw="3.50", away_win="5.00")
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "1.50" in prompt

    def test_prompt_includes_venue_when_set(self):
        team = TeamFactory(venue="Anfield")
        match = MatchFactory(home_team=team)
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "Anfield" in prompt

    def test_prompt_skips_venue_when_blank(self):
        team = TeamFactory(venue="")
        match = MatchFactory(home_team=team)
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "Venue:" not in prompt

    def test_prompt_includes_h2h_when_stats_exist(self):
        match = MatchFactory()
        MatchStatsFactory(
            match=match,
            h2h_summary_json={"total": 10, "home_wins": 4, "draws": 3, "away_wins": 3},
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "H2H" in prompt

    def test_prompt_includes_form_when_stats_exist(self):
        match = MatchFactory()
        MatchStatsFactory(
            match=match,
            home_form_json=[{"result": "W"}, {"result": "W"}, {"result": "L"}],
            away_form_json=[{"result": "D"}, {"result": "W"}],
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.PRE_MATCH)
        assert "form:" in prompt

    def test_post_bet_prompt_includes_bet_details(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot)
        match = MatchFactory()
        OddsFactory(match=match, home_win="1.60")
        from betting.tests.factories import BetSlipFactory
        bet = BetSlipFactory(
            user=bot, match=match,
            selection=BetSlip.Selection.HOME_WIN,
            odds_at_placement="1.60",
            stake="50.00",
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_BET, bet)
        assert "1.60" in prompt
        assert "50.00" in prompt
        assert "reacting to the bet" in prompt

    def test_post_match_prompt_includes_score(self):
        match = MatchFactory(
            status=Match.Status.FINISHED, home_score=2, away_score=1
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH)
        assert "2-1" in prompt
        assert "reacting to the final result" in prompt

    def test_post_match_prompt_includes_won_bet(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot)
        match = MatchFactory(status=Match.Status.FINISHED, home_score=1, away_score=0)
        from betting.tests.factories import BetSlipFactory
        bet = BetSlipFactory(
            user=bot, match=match,
            selection=BetSlip.Selection.HOME_WIN,
            status=BetSlip.Status.WON,
            payout="80.00",
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH, bet)
        assert "WON" in prompt
        assert "80.00" in prompt

    def test_post_match_prompt_includes_lost_bet(self):
        bot = BotUserFactory()
        UserBalanceFactory(user=bot)
        match = MatchFactory(status=Match.Status.FINISHED, home_score=0, away_score=2)
        from betting.tests.factories import BetSlipFactory
        bet = BetSlipFactory(
            user=bot, match=match,
            selection=BetSlip.Selection.HOME_WIN,
            status=BetSlip.Status.LOST,
            payout=None,
        )
        prompt = _build_user_prompt(match, BotComment.TriggerType.POST_MATCH, bet)
        assert "LOST" in prompt


# ---------------------------------------------------------------------------
# select_bots_for_match
# ---------------------------------------------------------------------------

class TestSelectBotsForMatch:
    def test_returns_at_most_max_bots(self):
        # Create several always-eligible bots
        BotUserFactory(email="parlaypete@bots.eplbets.local")
        BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        BotUserFactory(email="allinalice@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.SCHEDULED)

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH, max_bots=2)

        assert len(result) <= 2

    def test_excludes_bots_who_already_commented(self):
        bot = BotUserFactory(email="chaoscharlie@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.SCHEDULED)
        # Simulate an existing comment record
        BotComment.objects.create(
            user=bot, match=match, trigger_type=BotComment.TriggerType.PRE_MATCH,
            error="test",
        )

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)

        assert bot not in result

    def test_returns_empty_when_no_eligible_bots(self):
        match = MatchFactory(status=Match.Status.SCHEDULED)
        # No bots in DB
        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)
        assert result == []

    def test_excludes_bots_without_persona(self):
        # Bot with email not in BOT_PERSONA_PROMPTS
        BotUserFactory(email="ghost@bots.eplbets.local")
        match = MatchFactory(status=Match.Status.SCHEDULED)

        result = select_bots_for_match(match, BotComment.TriggerType.PRE_MATCH)

        assert result == []


# ---------------------------------------------------------------------------
# generate_bot_comment
# ---------------------------------------------------------------------------

class TestGenerateBotComment:
    def _make_bot_and_match(self, email="chaoscharlie@bots.eplbets.local"):
        bot = BotUserFactory(email=email)
        match = MatchFactory(status=Match.Status.SCHEDULED)
        OddsFactory(match=match)
        return bot, match

    def _mock_api_response(self, text):
        mock_content = MagicMock()
        mock_content.text = text
        mock_response = MagicMock()
        mock_response.content = [mock_content]
        return mock_response

    def test_creates_comment_on_success(self):
        bot, match = self._make_bot_and_match()
        good_text = "this match is going to be an absolute banger"

        with patch("bots.comment_service.anthropic.Anthropic") as mock_client_cls:
            mock_client_cls.return_value.messages.create.return_value = (
                self._mock_api_response(good_text)
            )
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                comment = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert comment is not None
        assert comment.body == good_text
        assert Comment.objects.filter(user=bot, match=match).count() == 1
        bc = BotComment.objects.get(user=bot, match=match)
        assert bc.comment == comment
        assert bc.filtered is False

    def test_dedup_prevents_second_comment(self):
        bot, match = self._make_bot_and_match()
        BotComment.objects.create(
            user=bot, match=match,
            trigger_type=BotComment.TriggerType.PRE_MATCH,
            error="existing",
        )

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        assert Comment.objects.filter(user=bot, match=match).count() == 0

    def test_returns_none_for_bot_without_persona(self):
        bot = BotUserFactory(email="nobody@bots.eplbets.local")
        match = MatchFactory()

        result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        assert BotComment.objects.count() == 0

    def test_returns_none_and_logs_when_no_api_key(self):
        bot, match = self._make_bot_and_match()

        with patch("django.conf.settings.ANTHROPIC_API_KEY", ""):
            result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        bc = BotComment.objects.get(user=bot, match=match)
        assert "ANTHROPIC_API_KEY" in bc.error

    def test_returns_none_and_logs_on_api_error(self):
        bot, match = self._make_bot_and_match()

        with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = Exception("timeout")
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        bc = BotComment.objects.get(user=bot, match=match)
        assert bc.error == "API call failed"
        assert bc.comment is None

    def test_returns_none_when_filter_rejects_response(self):
        bot, match = self._make_bot_and_match()
        bad_text = "hi"  # too short

        with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                self._mock_api_response(bad_text)
            )
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                result = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert result is None
        bc = BotComment.objects.get(user=bot, match=match)
        assert bc.filtered is True
        assert bc.raw_response == bad_text
        assert bc.comment is None

    def test_strips_whitespace_from_api_response(self):
        bot, match = self._make_bot_and_match()
        padded = "  this match is a real draw merchant special  "

        with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                self._mock_api_response(padded)
            )
            with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                comment = generate_bot_comment(bot, match, BotComment.TriggerType.PRE_MATCH)

        assert comment is not None
        assert comment.body == padded.strip()

    def test_different_trigger_types_are_independent(self):
        bot, match = self._make_bot_and_match()
        good_text = "this match is going to be an absolute banger"

        for trigger in [
            BotComment.TriggerType.PRE_MATCH,
            BotComment.TriggerType.POST_BET,
            BotComment.TriggerType.POST_MATCH,
        ]:
            with patch("bots.comment_service.anthropic.Anthropic") as mock_cls:
                mock_cls.return_value.messages.create.return_value = (
                    self._mock_api_response(good_text)
                )
                with patch("django.conf.settings.ANTHROPIC_API_KEY", "sk-test"):
                    generate_bot_comment(bot, match, trigger)

        assert BotComment.objects.filter(user=bot, match=match).count() == 3
        assert Comment.objects.filter(user=bot, match=match).count() == 3
