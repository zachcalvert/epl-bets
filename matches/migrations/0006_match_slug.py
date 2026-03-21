from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0005_match_notes_body_blank"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="slug",
            field=models.SlugField(
                blank=True,
                default="",
                max_length=50,
                verbose_name="slug",
            ),
        ),
    ]
