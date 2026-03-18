import core.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeatureFlag",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "id_hash",
                    models.CharField(
                        default=core.models.generate_short_id,
                        editable=False,
                        help_text="Unique 8-character identifier for client-side use",
                        max_length=8,
                        unique=True,
                        verbose_name="ID Hash",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated at")),
                (
                    "name",
                    models.SlugField(
                        help_text="Unique slug identifier used in code (e.g. 'enhanced-match-stats').",
                        max_length=100,
                        unique=True,
                        verbose_name="name",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Human-readable explanation of what this flag controls.",
                        verbose_name="description",
                    ),
                ),
                (
                    "is_enabled_for_all",
                    models.BooleanField(
                        default=False,
                        help_text="When checked, this flag is active for every user regardless of the user list below.",
                        verbose_name="enabled for all users",
                    ),
                ),
                (
                    "users",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Individual users for whom this flag is explicitly enabled.",
                        related_name="feature_flags",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="enabled for users",
                    ),
                ),
            ],
            options={
                "verbose_name": "feature flag",
                "verbose_name_plural": "feature flags",
                "ordering": ["name"],
            },
        ),
    ]
