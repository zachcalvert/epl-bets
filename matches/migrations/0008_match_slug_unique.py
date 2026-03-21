from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0007_populate_match_slugs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="match",
            name="slug",
            field=models.SlugField(
                max_length=50,
                unique=True,
                verbose_name="slug",
            ),
        ),
    ]
