from django.db import migrations


def populate_match_slugs(apps, schema_editor):
    Match = apps.get_model("matches", "Match")
    seen = {}
    for match in Match.objects.select_related("home_team", "away_team").order_by("kickoff"):
        home = (match.home_team.tla or match.home_team.short_name or "xxx").lower()
        away = (match.away_team.tla or match.away_team.short_name or "xxx").lower()
        date_str = match.kickoff.strftime("%Y-%m-%d")
        base = f"{home}-{away}-{date_str}"
        slug = base
        counter = seen.get(base, 1)
        if counter > 1:
            slug = f"{base}-{counter}"
        seen[base] = counter + 1
        match.slug = slug
        match.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0006_match_slug"),
    ]

    operations = [
        migrations.RunPython(populate_match_slugs, migrations.RunPython.noop),
    ]
