from django.conf import settings
from django.core.management.base import BaseCommand

from betting.services import sync_odds
from matches.services import sync_matches, sync_standings, sync_teams


class Command(BaseCommand):
    help = "Seed the database with EPL data from football-data.org and The Odds API"

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            default=settings.CURRENT_SEASON,
            help="Season start year, e.g. 2025 for 2025-26 (default: %(default)s)",
        )
        parser.add_argument(
            "--skip-odds",
            action="store_true",
            help="Skip fetching odds (saves Odds API credits)",
        )
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Seed from bundled static JSON instead of calling APIs",
        )

    def handle(self, *args, **options):
        season = options["season"]
        offline = options["offline"]
        skip_odds = options["skip_odds"]

        mode = "offline" if offline else "live"
        self.stdout.write(f"Seeding EPL data (season={season}, mode={mode})")
        self.stdout.write("")

        # Teams
        self.stdout.write("Syncing teams...")
        created, updated = sync_teams(season, offline=offline)
        self.stdout.write(self.style.SUCCESS(f"  Teams: {created} created, {updated} updated"))

        # Matches
        self.stdout.write("Syncing matches...")
        created, updated = sync_matches(season, offline=offline)
        self.stdout.write(self.style.SUCCESS(f"  Matches: {created} created, {updated} updated"))

        # Standings
        self.stdout.write("Syncing standings...")
        created, updated = sync_standings(season, offline=offline)
        self.stdout.write(self.style.SUCCESS(f"  Standings: {created} created, {updated} updated"))

        # Odds
        if skip_odds:
            self.stdout.write(self.style.WARNING("  Odds: skipped (--skip-odds)"))
        elif offline:
            self.stdout.write(self.style.WARNING("  Odds: skipped (offline mode)"))
        else:
            self.stdout.write("Syncing odds...")
            created, updated = sync_odds()
            self.stdout.write(self.style.SUCCESS(f"  Odds: {created} created, {updated} updated"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done!"))
