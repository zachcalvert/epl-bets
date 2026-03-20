"""Celery tasks for bot-generated board posts.

Each task selects one bot based on context and recency, builds an LLM prompt
with league context, and creates a BoardPost.
"""

import logging
import random

import anthropic
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

from activity.services import queue_activity_event
from board.context import format_board_context_for_prompt, get_board_context
from board.models import BoardPost, PostType
from bots.models import BotProfile

User = get_user_model()
logger = logging.getLogger(__name__)

# Post type -> which strategy types are eligible
POST_TYPE_STRATEGY_POOLS = {
    PostType.RESULTS_TABLE: [
        BotProfile.StrategyType.HOMER,
        BotProfile.StrategyType.VALUE_HUNTER,
    ],
    PostType.PREDICTION: list(BotProfile.StrategyType),  # all strategies
    PostType.META: [
        BotProfile.StrategyType.CHAOS_AGENT,
        BotProfile.StrategyType.PARLAY,
    ],
}

# Prompt templates per trigger type
PROMPT_TEMPLATES = {
    "postgw": (
        "You are posting on a community message board for an EPL betting site. "
        "Write a post reacting to the latest gameweek results. Focus on what the "
        "table looks like now — title race, relegation battle, who's in form, who's "
        "bottling it. This is NOT a recap. It's your take on what it all MEANS.\n\n"
        "{context}\n\n"
        "Write a short, opinionated board post (2-4 sentences max). "
        "Output ONLY the post text."
    ),
    "midweek_prediction": (
        "You are posting on a community message board for an EPL betting site. "
        "Write a midweek prediction post about the upcoming fixtures. Who's going "
        "to surprise people? Where's the value? What match should everyone watch?\n\n"
        "{context}\n\n"
        "Write a short, opinionated board post (2-4 sentences max). "
        "Output ONLY the post text."
    ),
    "weekend_preview": (
        "You are posting on a community message board for an EPL betting site. "
        "Write a weekend preview hyping the upcoming matches. Pick a match or two "
        "to focus on. Make a bold call. Get people excited (or worried).\n\n"
        "{context}\n\n"
        "Write a short, opinionated board post (2-4 sentences max). "
        "Output ONLY the post text."
    ),
    "season_outlook": (
        "You are posting on a community message board for an EPL betting site. "
        "Write a big-picture season outlook post. Where does the title race stand? "
        "Who's overperforming or underperforming? Any bold predictions for the rest "
        "of the season?\n\n"
        "{context}\n\n"
        "Write a short, opinionated board post (3-5 sentences max). "
        "Output ONLY the post text."
    ),
}


def _get_last_board_poster():
    """Return the author_id of the most recent bot board post, or None."""
    last = (
        BoardPost.objects.filter(author__is_bot=True, parent__isnull=True)
        .order_by("-created_at")
        .values_list("author_id", flat=True)
        .first()
    )
    return last


def _select_bot(post_type, prefer_homer_tla=None):
    """Select one bot for the given post type, avoiding back-to-back repeats.

    Args:
        post_type: PostType value
        prefer_homer_tla: If set, prefer the homer bot for this team TLA
    """
    strategy_types = POST_TYPE_STRATEGY_POOLS.get(
        post_type, list(BotProfile.StrategyType),
    )
    last_poster_id = _get_last_board_poster()

    eligible = BotProfile.objects.filter(
        is_active=True,
        strategy_type__in=strategy_types,
        user__is_active=True,
        persona_prompt__gt="",
    ).select_related("user")

    # If we have a TLA preference, try that homer bot first
    if prefer_homer_tla:
        homer = eligible.filter(team_tla=prefer_homer_tla).first()
        if homer and homer.user_id != last_poster_id:
            return homer.user

    # General selection from pool
    candidates = [
        bp.user for bp in eligible
        if bp.user_id != last_poster_id
    ]

    if not candidates:
        # Fall back: allow the last poster if no other options
        candidates = [bp.user for bp in eligible]

    return random.choice(candidates) if candidates else None


def _generate_board_post(bot_user, post_type, prompt_key):
    """Generate and create a board post via the LLM.

    Returns the created BoardPost or None.
    """
    profile = getattr(bot_user, "bot_profile", None)
    if not profile:
        try:
            profile = BotProfile.objects.get(user=bot_user)
        except BotProfile.DoesNotExist:
            pass
    system_prompt = profile.persona_prompt if profile else None
    if not system_prompt:
        logger.warning("No persona prompt for bot %s", bot_user.email)
        return None

    ctx = get_board_context()
    context_str = format_board_context_for_prompt(ctx)
    template = PROMPT_TEMPLATES.get(prompt_key, PROMPT_TEMPLATES["midweek_prediction"])
    user_prompt = template.format(context=context_str)

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not configured")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            temperature=0.9,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text.strip()
    except Exception:
        logger.exception("Claude API call failed for board post by %s", bot_user.display_name)
        return None

    # Basic length filter
    if len(raw_text) < 10 or len(raw_text) > 1500:
        logger.info("Board post filtered (length=%d): %s", len(raw_text), bot_user.display_name)
        return None

    post = BoardPost.objects.create(
        author=bot_user,
        post_type=post_type,
        body=raw_text,
    )

    queue_activity_event(
        "bot_board_post",
        f"{bot_user.display_name} posted on the board",
        url="/board/",
        icon="newspaper",
    )

    logger.info(
        "Bot %s posted %s board post: %r",
        bot_user.display_name, post_type, raw_text[:80],
    )
    return post


@shared_task
def generate_postgw_board_post():
    """Post-gameweek wrap-up — fires Sunday ~21:00 UTC."""
    bot = _select_bot(PostType.RESULTS_TABLE)
    if not bot:
        return "no eligible bot"

    post = _generate_board_post(bot, PostType.RESULTS_TABLE, "postgw")
    return f"posted by {bot.display_name}" if post else "skipped"


@shared_task
def generate_midweek_prediction_post():
    """Midweek prediction — fires Wednesday morning."""
    bot = _select_bot(PostType.PREDICTION)
    if not bot:
        return "no eligible bot"

    post = _generate_board_post(bot, PostType.PREDICTION, "midweek_prediction")
    return f"posted by {bot.display_name}" if post else "skipped"


@shared_task
def generate_weekend_preview_post():
    """Weekend preview — fires Friday ~09:00 UTC."""
    bot = _select_bot(PostType.PREDICTION)
    if not bot:
        return "no eligible bot"

    post = _generate_board_post(bot, PostType.PREDICTION, "weekend_preview")
    return f"posted by {bot.display_name}" if post else "skipped"


@shared_task
def generate_season_outlook_post():
    """Monthly season outlook — fires ~1st of month."""
    bot = _select_bot(PostType.PREDICTION)
    if not bot:
        return "no eligible bot"

    post = _generate_board_post(bot, PostType.PREDICTION, "season_outlook")
    return f"posted by {bot.display_name}" if post else "skipped"


@shared_task
def generate_bot_feature_request_post():
    """Bi-weekly bot feature request — stubbed.

    Scaffolded for future activation. When implemented, a bot from the META
    pool will post a tongue-in-cheek feature request in character.
    """
    # TODO: implement bot feature request prompt
    logger.info("Bot feature request post: stubbed, skipping")
    return "stubbed"
