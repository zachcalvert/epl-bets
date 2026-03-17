"""Celery tasks for running bot betting strategies."""

import logging
import random

from celery import shared_task
from django.contrib.auth import get_user_model

from bots.registry import get_strategy_for_bot
from bots.services import (
    get_available_matches_for_bot,
    get_best_odds_map,
    get_full_odds_map,
    maybe_topup_bot,
    place_bot_bet,
    place_bot_parlay,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task
def run_bot_strategies():
    """Dispatch individual bot strategy tasks with staggered delays."""
    bot_users = User.objects.filter(is_bot=True, is_active=True)
    count = 0

    for bot in bot_users:
        delay = random.randint(120, 1800)  # 2-30 minutes
        execute_bot_strategy.apply_async(args=[bot.pk], countdown=delay)
        count += 1

    logger.info("Dispatched %d bot strategy tasks", count)
    return f"dispatched {count} bot tasks"


@shared_task(bind=True, max_retries=1)
def execute_bot_strategy(self, bot_user_id):
    """Run a single bot's strategy and place its bets."""
    try:
        user = User.objects.get(pk=bot_user_id, is_bot=True, is_active=True)
    except User.DoesNotExist:
        logger.warning("Bot user %s not found or inactive", bot_user_id)
        return "bot not found"

    strategy = get_strategy_for_bot(user)
    if not strategy:
        logger.warning("No strategy registered for bot %s", user.email)
        return "no strategy"

    # Top up if broke
    maybe_topup_bot(user)

    # Get available matches
    available = get_available_matches_for_bot(user)
    if not available.exists():
        return "no matches"

    match_ids = list(available.values_list("pk", flat=True))
    odds_map = get_best_odds_map(match_ids)

    if not odds_map:
        return "no odds"

    # ValueHunter needs full per-bookmaker odds
    from bots.strategies import ValueHunterStrategy

    if isinstance(strategy, ValueHunterStrategy):
        odds_map["_full"] = get_full_odds_map(match_ids)

    # Get current balance for stake calculations
    from betting.models import UserBalance

    try:
        balance = UserBalance.objects.get(user=user).balance
    except UserBalance.DoesNotExist:
        return "no balance"

    # Place single bets
    bets_placed = 0
    picks = strategy.pick_bets(available, odds_map, balance)
    for pick in picks:
        result = place_bot_bet(user, pick.match_id, pick.selection, pick.stake)
        if result:
            bets_placed += 1

    # Place parlays
    parlays_placed = 0
    parlay_picks = strategy.pick_parlays(available, odds_map, balance)
    for pp in parlay_picks:
        result = place_bot_parlay(user, pp.legs, pp.stake)
        if result:
            parlays_placed += 1

    summary = f"{user.display_name}: {bets_placed} bets, {parlays_placed} parlays"
    logger.info("Bot run complete: %s", summary)
    return summary
