from django.db import migrations


def seed_example_flag(apps, schema_editor):
    """Seed a trivial example feature flag to demonstrate the system."""
    FeatureFlag = apps.get_model("flags", "FeatureFlag")
    FeatureFlag.objects.get_or_create(
        name="enhanced-match-stats",
        defaults={
            "description": (
                "Show enhanced match statistics (possession, shots, xG) on the "
                "match detail page. Enable per-user to trial before a full rollout."
            ),
            "is_enabled_for_all": False,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("flags", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_example_flag,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
