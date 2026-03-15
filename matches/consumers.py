import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer
from django.db import close_old_connections
from django.db.models import Min
from django.template.loader import render_to_string

from betting.models import Odds
from matches.models import Match

logger = logging.getLogger(__name__)


class LiveUpdatesConsumer(WebsocketConsumer):
    """
    Single WebSocket consumer handling all real-time page updates.

    Clients connect with a scope parameter:
      - "dashboard" → joins the "live_scores" group (all live match updates)
      - "<match_pk>" → joins "match_<pk>" group (single match updates)

    The consumer receives events from Celery tasks via the channel layer
    and renders OOB-swap HTML partials to push to the client.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.groups_joined = []
        self.scope_param = None

    def connect(self):
        self.scope_param = self.scope["url_route"]["kwargs"]["scope"]
        self.accept()

        if self.scope_param == "dashboard":
            self._join_group("live_scores")
        elif self.scope_param.isdigit():
            self._join_group(f"match_{self.scope_param}")
        else:
            logger.warning("LiveUpdatesConsumer: unknown scope %s", self.scope_param)

    def disconnect(self, close_code):
        for group in self.groups_joined:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_discard)(group, self.channel_name)
        self.groups_joined.clear()

    def _join_group(self, group_name):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)(group_name, self.channel_name)
        self.groups_joined.append(group_name)

    # ── Channel layer event handlers ──

    def score_update(self, event):
        """Handle score updates for the dashboard (match card OOB swap)."""
        close_old_connections()
        match_id = event["match_id"]
        try:
            match = (
                Match.objects.filter(pk=match_id)
                .select_related("home_team", "away_team")
                .first()
            )
            if not match:
                return

            # Annotate best odds
            best = (
                Odds.objects.filter(match_id=match_id)
                .aggregate(
                    best_home=Min("home_win"),
                    best_draw=Min("draw"),
                    best_away=Min("away_win"),
                )
            )
            match.best_home_odds = best.get("best_home")
            match.best_draw_odds = best.get("best_draw")
            match.best_away_odds = best.get("best_away")

            html = render_to_string(
                "matches/partials/match_card_oob.html", {"match": match}
            )
            self.send(text_data=html)
        except Exception:
            logger.exception("Error rendering score_update for match %s", match_id)

    def match_score_update(self, event):
        """Handle score updates for the match detail page (score display OOB swap)."""
        close_old_connections()
        match_id = event["match_id"]
        try:
            match = (
                Match.objects.filter(pk=match_id)
                .select_related("home_team", "away_team")
                .first()
            )
            if not match:
                return

            html = render_to_string(
                "matches/partials/score_display_oob.html", {"match": match}
            )
            self.send(text_data=html)
        except Exception:
            logger.exception(
                "Error rendering match_score_update for match %s", match_id
            )
