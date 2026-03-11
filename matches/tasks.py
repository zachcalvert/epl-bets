import logging

from celery import shared_task
from django.conf import settings

from matches.services import sync_matches, sync_standings, sync_teams

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_teams(self):
    logger.info("fetch_teams: starting")
    try:
        created, updated = sync_teams(settings.CURRENT_SEASON)
        logger.info("fetch_teams: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_teams failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_fixtures(self):
    logger.info("fetch_fixtures: starting")
    try:
        created, updated = sync_matches(settings.CURRENT_SEASON)
        logger.info("fetch_fixtures: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_fixtures failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_standings(self):
    logger.info("fetch_standings: starting")
    try:
        created, updated = sync_standings(settings.CURRENT_SEASON)
        logger.info("fetch_standings: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_standings failed")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def fetch_live_scores(self):
    logger.info("fetch_live_scores: starting")
    try:
        created, updated = sync_matches(settings.CURRENT_SEASON, status="LIVE")
        logger.info("fetch_live_scores: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_live_scores failed")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
