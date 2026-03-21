from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_user_show_activity_toasts"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="id_hash",
            field=models.CharField(
                default=core.models.generate_short_id,
                editable=False,
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                max_length=70,
            ),
        ),
    ]
