from unittest.mock import MagicMock, patch

import pytest

from board.models import BoardPost, PostType
from board.tasks import (
    _generate_board_post,
    _get_last_board_poster,
    _select_bot,
    generate_bot_feature_request_post,
    generate_midweek_prediction_post,
    generate_postgw_board_post,
    generate_season_outlook_post,
    generate_weekend_preview_post,
)
from bots.models import BotProfile
from bots.tests.factories import BotUserFactory

pytestmark = pytest.mark.django_db


# --- _get_last_board_poster ---


def test_get_last_board_poster_returns_none_when_no_posts():
    assert _get_last_board_poster() is None


def test_get_last_board_poster_returns_most_recent_bot_poster():
    bot1 = BotUserFactory()
    bot2 = BotUserFactory()
    BoardPost.objects.create(author=bot1, post_type=PostType.META, body="First")
    BoardPost.objects.create(author=bot2, post_type=PostType.META, body="Second")

    assert _get_last_board_poster() == bot2.pk


def test_get_last_board_poster_ignores_replies():
    bot1 = BotUserFactory()
    bot2 = BotUserFactory()
    parent = BoardPost.objects.create(author=bot1, post_type=PostType.META, body="Top")
    BoardPost.objects.create(
        author=bot2, post_type=PostType.META, body="Reply", parent=parent
    )

    # bot1 is the last top-level poster
    assert _get_last_board_poster() == bot1.pk


# --- _select_bot ---


def test_select_bot_returns_none_when_no_candidates():
    # No bots with matching strategy type for META (chaos_agent, parlay)
    result = _select_bot(PostType.META)

    assert result is None


def test_select_bot_avoids_last_poster():
    bot1 = BotUserFactory(bot_profile__strategy_type=BotProfile.StrategyType.CHAOS_AGENT)
    bot2 = BotUserFactory(bot_profile__strategy_type=BotProfile.StrategyType.PARLAY)

    # Make bot1 the last poster
    BoardPost.objects.create(author=bot1, post_type=PostType.META, body="last")

    result = _select_bot(PostType.META)

    assert result == bot2


def test_select_bot_with_homer_tla_preference():
    bot = BotUserFactory(
        bot_profile__strategy_type=BotProfile.StrategyType.HOMER,
        bot_profile__team_tla="ARS",
    )

    result = _select_bot(PostType.RESULTS_TABLE, prefer_homer_tla="ARS")

    assert result == bot


# --- _generate_board_post ---


@patch("board.tasks.anthropic")
@patch("board.tasks.get_board_context")
def test_generate_board_post_creates_post(mock_ctx, mock_anthropic, settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
    mock_ctx.return_value = {
        "standings": [],
        "last_gw_results": [],
        "upcoming_fixtures": [],
        "current_matchday": None,
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Arsenal will win the league, guaranteed.")]
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    post = _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")

    assert post is not None
    assert post.author == bot
    assert post.post_type == PostType.PREDICTION
    assert post.body == "Arsenal will win the league, guaranteed."


@patch("board.tasks.anthropic")
@patch("board.tasks.get_board_context")
def test_generate_board_post_filters_short_text(mock_ctx, mock_anthropic, settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
    mock_ctx.return_value = {
        "standings": [],
        "last_gw_results": [],
        "upcoming_fixtures": [],
        "current_matchday": None,
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Short")]
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    post = _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")

    assert post is None
    assert BoardPost.objects.count() == 0


@patch("board.tasks.anthropic")
@patch("board.tasks.get_board_context")
def test_generate_board_post_filters_long_text(mock_ctx, mock_anthropic, settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
    mock_ctx.return_value = {
        "standings": [],
        "last_gw_results": [],
        "upcoming_fixtures": [],
        "current_matchday": None,
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="x" * 1501)]
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    post = _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")

    assert post is None


def test_generate_board_post_returns_none_for_missing_persona():
    # Create a bot user WITHOUT a bot_profile (no persona prompt)
    bot = BotUserFactory(bot_profile=None)

    post = _generate_board_post(bot, PostType.META, "midweek_prediction")

    assert post is None


@patch("board.tasks.anthropic")
@patch("board.tasks.get_board_context")
def test_generate_board_post_returns_none_without_api_key(
    mock_ctx, mock_anthropic, settings
):
    settings.ANTHROPIC_API_KEY = ""
    bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
    mock_ctx.return_value = {
        "standings": [],
        "last_gw_results": [],
        "upcoming_fixtures": [],
        "current_matchday": None,
    }

    post = _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")

    assert post is None


@patch("board.tasks.anthropic")
@patch("board.tasks.get_board_context")
def test_generate_board_post_handles_api_error(mock_ctx, mock_anthropic, settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
    mock_ctx.return_value = {
        "standings": [],
        "last_gw_results": [],
        "upcoming_fixtures": [],
        "current_matchday": None,
    }
    mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception(
        "API down"
    )

    post = _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")

    assert post is None


@patch("board.tasks.anthropic")
@patch("board.tasks.get_board_context")
def test_generate_board_post_queues_activity_event(mock_ctx, mock_anthropic, settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    bot = BotUserFactory(email="frontrunner@bots.eplbets.local")
    mock_ctx.return_value = {
        "standings": [],
        "last_gw_results": [],
        "upcoming_fixtures": [],
        "current_matchday": None,
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="A solid hot take about the league.")]
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    with patch("board.tasks.queue_activity_event") as mock_queue:
        _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")

        mock_queue.assert_called_once_with(
            "bot_board_post",
            f"{bot.display_name} posted on the board",
            url="/board/",
            icon="newspaper",
        )


# --- Shared task wrappers ---


@patch("board.tasks._generate_board_post")
@patch("board.tasks._select_bot")
def test_generate_postgw_board_post_no_bot(mock_select, mock_generate):
    mock_select.return_value = None

    result = generate_postgw_board_post()

    assert result == "no eligible bot"
    mock_generate.assert_not_called()


@patch("board.tasks._generate_board_post")
@patch("board.tasks._select_bot")
def test_generate_postgw_board_post_success(mock_select, mock_generate):
    bot = MagicMock(display_name="ChalkEater")
    mock_select.return_value = bot
    mock_generate.return_value = MagicMock()

    result = generate_postgw_board_post()

    assert "ChalkEater" in result
    mock_generate.assert_called_once_with(bot, PostType.RESULTS_TABLE, "postgw")


@patch("board.tasks._generate_board_post")
@patch("board.tasks._select_bot")
def test_generate_midweek_prediction_post_no_bot(mock_select, mock_generate):
    mock_select.return_value = None

    result = generate_midweek_prediction_post()

    assert result == "no eligible bot"


@patch("board.tasks._generate_board_post")
@patch("board.tasks._select_bot")
def test_generate_midweek_prediction_post_skipped(mock_select, mock_generate):
    mock_select.return_value = MagicMock(display_name="Bot")
    mock_generate.return_value = None

    result = generate_midweek_prediction_post()

    assert result == "skipped"


@patch("board.tasks._generate_board_post")
@patch("board.tasks._select_bot")
def test_generate_weekend_preview_post(mock_select, mock_generate):
    bot = MagicMock(display_name="Bot")
    mock_select.return_value = bot
    mock_generate.return_value = MagicMock()

    result = generate_weekend_preview_post()

    assert "Bot" in result
    mock_generate.assert_called_once_with(bot, PostType.PREDICTION, "weekend_preview")


@patch("board.tasks._generate_board_post")
@patch("board.tasks._select_bot")
def test_generate_season_outlook_post(mock_select, mock_generate):
    bot = MagicMock(display_name="Outlook")
    mock_select.return_value = bot
    mock_generate.return_value = MagicMock()

    result = generate_season_outlook_post()

    assert "Outlook" in result
    mock_generate.assert_called_once_with(bot, PostType.PREDICTION, "season_outlook")


def test_generate_bot_feature_request_post_is_stubbed():
    result = generate_bot_feature_request_post()

    assert result == "stubbed"
