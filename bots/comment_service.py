"""Bot comment generation service — generates and posts LLM-powered comments.

Uses the Anthropic Claude API to generate personality-driven match comments
for bot users. Each comment is tracked via BotComment for dedup and debugging.
"""

import logging
import random
import re

import anthropic
from django.conf import settings
from django.contrib.auth import get_user_model

from betting.models import BetSlip, Odds
from bots.models import BotComment
from bots.personas import BOT_PERSONA_PROMPTS
from bots.services import get_best_odds_map
from discussions.models import Comment
from matches.models import MatchStats

User = get_user_model()
logger = logging.getLogger(__name__)

# Words that should never appear in bot comments
PROFANITY_BLOCKLIST = {
    "fuck", "shit", "bitch", "bastard", "asshole", "cunt", "dick", "piss",
    "slut", "whore", "retard", "faggot", "nigger", "nigga", "spic", "chink",
    "kike",
}

# At least one of these must appear (case-insensitive) for relevance check
FOOTBALL_KEYWORDS = {
    "match", "goal", "goals", "win", "draw", "loss", "nil", "odds", "bet",
    "form", "league", "premier", "epl", "kickoff", "kick", "half", "full",
    "time", "score", "clean sheet", "derby", "relegation", "promoted",
    "champions", "top", "bottom", "table", "points", "gd", "xg", "expected",
    "parlay", "stake", "payout", "underdog", "favourite", "favorite",
    "upset", "bottle", "bottled", "fraud", "frauds", "merchant", "tax",
    "copium", "scenes", "inject", "lock", "locks", "chalk", "degen",
    "comeback", "banger", "shithouse", "masterclass",
}


def generate_bot_comment(bot_user, match, trigger_type, bet_slip=None):
    """Generate and post an LLM-powered comment for a bot user.

    Returns the created Comment if successful, None otherwise.
    Dedup is enforced by the BotComment unique constraint.
    """
    # Check dedup
    if BotComment.objects.filter(
        user=bot_user, match=match, trigger_type=trigger_type
    ).exists():
        logger.debug(
            "BotComment already exists: %s / %s / %s",
            bot_user.display_name, match, trigger_type,
        )
        return None

    # Build prompts
    system_prompt = BOT_PERSONA_PROMPTS.get(bot_user.email)
    if not system_prompt:
        logger.warning("No persona prompt for bot %s", bot_user.email)
        return None

    user_prompt = _build_user_prompt(match, trigger_type, bet_slip)
    full_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"

    # Call Claude API
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not configured")
        BotComment.objects.create(
            user=bot_user, match=match, trigger_type=trigger_type,
            prompt_used=full_prompt, error="ANTHROPIC_API_KEY not configured",
        )
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            temperature=0.9,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = response.content[0].text.strip()
    except Exception:
        logger.exception("Claude API call failed for bot %s", bot_user.display_name)
        BotComment.objects.create(
            user=bot_user, match=match, trigger_type=trigger_type,
            prompt_used=full_prompt, error="API call failed",
        )
        return None

    # Post-hoc filter
    ok, reason = _filter_comment(raw_text, match)
    if not ok:
        logger.info(
            "Bot comment filtered out (%s): %s — %r",
            reason, bot_user.display_name, raw_text[:100],
        )
        BotComment.objects.create(
            user=bot_user, match=match, trigger_type=trigger_type,
            prompt_used=full_prompt, raw_response=raw_text, filtered=True,
            error=reason,
        )
        return None

    # Post the comment
    comment = Comment.objects.create(
        match=match,
        user=bot_user,
        body=raw_text,
    )
    BotComment.objects.create(
        user=bot_user, match=match, trigger_type=trigger_type,
        prompt_used=full_prompt, raw_response=raw_text, comment=comment,
    )
    logger.info(
        "Bot %s posted %s comment on %s: %r",
        bot_user.display_name, trigger_type, match, raw_text[:80],
    )
    return comment


def select_bots_for_match(match, trigger_type, max_bots=2):
    """Pick 1-2 relevant bots for a match + trigger, excluding those who already commented."""
    already_commented = set(
        BotComment.objects.filter(match=match, trigger_type=trigger_type)
        .values_list("user_id", flat=True)
    )

    odds_map = get_best_odds_map([match.pk])
    match_odds = odds_map.get(match.pk, {})

    candidates = []
    for bot in User.objects.filter(is_bot=True, is_active=True):
        if bot.pk in already_commented:
            continue
        if bot.email not in BOT_PERSONA_PROMPTS:
            continue
        if _is_bot_relevant(bot, match, match_odds):
            candidates.append(bot)

    if not candidates:
        return []

    return random.sample(candidates, min(max_bots, len(candidates)))


def _is_bot_relevant(bot, match, match_odds):
    """Check if a bot's strategy makes them relevant to this match."""
    home = match_odds.get("home_win")
    draw = match_odds.get("draw")
    away = match_odds.get("away_win")

    email = bot.email
    if email == "frontrunner@bots.eplbets.local":
        # Relevant when there's a clear favorite
        if home and away:
            return min(home, away) < 1.80
    elif email == "underdog@bots.eplbets.local":
        # Relevant when there's a clear underdog
        if home and away:
            return max(home, away) >= 3.00
    elif email == "drawdoctor@bots.eplbets.local":
        # Relevant when draw odds are in the sweet spot
        if draw:
            return 2.80 <= float(draw) <= 3.80
    elif email == "valuehunter@bots.eplbets.local":
        # Relevant when there's odds spread — check if we have multiple bookmakers
        bookmaker_count = Odds.objects.filter(match=match).count()
        return bookmaker_count >= 2
    elif email in (
        "parlaypete@bots.eplbets.local",
        "chaoscharlie@bots.eplbets.local",
        "allinalice@bots.eplbets.local",
    ):
        # Always eligible
        return True
    else:
        # Homer bots — only relevant if their team is playing
        try:
            homer_team_id = bot.homer_config.team_id
            return match.home_team_id == homer_team_id or match.away_team_id == homer_team_id
        except Exception:
            return False

    return False


def _build_user_prompt(match, trigger_type, bet_slip=None):
    """Build the user prompt with match context for the LLM."""
    home = match.home_team
    away = match.away_team

    lines = [
        f"Match: {home.name} vs {away.name}",
        f"Kickoff: {match.kickoff.strftime('%a %d %b, %H:%M UTC')} | Matchday {match.matchday}",
    ]

    if home.venue:
        lines.append(f"Venue: {home.venue}")

    # Odds
    odds_map = get_best_odds_map([match.pk])
    match_odds = odds_map.get(match.pk, {})
    if match_odds:
        lines.append(
            f"Odds: {home.short_name or home.tla} {match_odds.get('home_win', '?')}"
            f" | Draw {match_odds.get('draw', '?')}"
            f" | {away.short_name or away.tla} {match_odds.get('away_win', '?')}"
        )

    # H2H and form
    try:
        stats = MatchStats.objects.get(match=match)
        h2h = stats.h2h_summary_json
        if h2h:
            lines.append(
                f"H2H (last {h2h.get('total', '?')}): "
                f"{home.short_name or home.tla} {h2h.get('home_wins', 0)}W "
                f"- {h2h.get('draws', 0)}D - "
                f"{away.short_name or away.tla} {h2h.get('away_wins', 0)}W"
            )
        if stats.home_form_json:
            form_str = " ".join(
                r.get("result", "?") for r in stats.home_form_json[:5]
            )
            lines.append(f"{home.short_name or home.tla} form: {form_str}")
        if stats.away_form_json:
            form_str = " ".join(
                r.get("result", "?") for r in stats.away_form_json[:5]
            )
            lines.append(f"{away.short_name or away.tla} form: {form_str}")
    except MatchStats.DoesNotExist:
        pass

    # Trigger-specific context
    if trigger_type == BotComment.TriggerType.POST_BET and bet_slip:
        selection_display = bet_slip.get_selection_display()
        lines.append(
            f"Your bet: {selection_display} @ {bet_slip.odds_at_placement} "
            f"for {bet_slip.stake} credits"
        )
        lines.append("")
        lines.append("Write a comment reacting to the bet you just placed on this match.")

    elif trigger_type == BotComment.TriggerType.POST_MATCH:
        lines.append(f"Final score: {home.name} {match.home_score}-{match.away_score} {away.name}")
        if bet_slip:
            won = bet_slip.status == BetSlip.Status.WON
            lines.append(
                f"Your bet: {bet_slip.get_selection_display()} @ {bet_slip.odds_at_placement} "
                f"— {'WON' if won else 'LOST'}"
            )
            if won and bet_slip.payout:
                lines.append(f"Payout: {bet_slip.payout} credits")
        lines.append("")
        lines.append("Write a comment reacting to the final result of this match.")

    elif trigger_type == BotComment.TriggerType.PRE_MATCH:
        lines.append("")
        lines.append("Write a pre-match hype comment about this upcoming match.")

    return "\n".join(lines)


def _filter_comment(text, match):
    """Lightweight post-hoc filter. Returns (ok, reason)."""
    if len(text) < 10:
        return False, "too_short"
    if len(text) > 500:
        return False, "too_long"

    text_lower = text.lower()

    # Profanity check
    for word in PROFANITY_BLOCKLIST:
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            return False, f"profanity:{word}"

    # Relevance — must mention a team name or football keyword
    home_name = match.home_team.name.lower()
    away_name = match.away_team.name.lower()
    home_short = (match.home_team.short_name or "").lower()
    away_short = (match.away_team.short_name or "").lower()
    home_tla = (match.home_team.tla or "").lower()
    away_tla = (match.away_team.tla or "").lower()

    team_terms = {home_name, away_name, home_short, away_short, home_tla, away_tla}
    team_terms.discard("")

    has_team = any(term in text_lower for term in team_terms)
    has_football = any(kw in text_lower for kw in FOOTBALL_KEYWORDS)

    if not has_team and not has_football:
        return False, "irrelevant"

    return True, ""
