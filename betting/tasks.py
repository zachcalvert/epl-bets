import logging

from celery import shared_task

from betting.services import sync_odds

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def fetch_odds(self):
    logger.info("fetch_odds: starting")
    try:
        created, updated = sync_odds()
        logger.info("fetch_odds: done created=%d updated=%d", created, updated)
    except Exception as exc:
        logger.exception("fetch_odds failed")
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))
