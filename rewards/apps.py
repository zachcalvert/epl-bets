from django.apps import AppConfig


class RewardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rewards"
    verbose_name = "Rewards"

    def ready(self):
        import rewards.signals  # noqa: F401
