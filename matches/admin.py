from django.contrib import admin

from matches.models import Match, Standing, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "tla", "venue"]
    search_fields = ["name", "short_name", "tla"]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "matchday", "kickoff", "season"]
    list_filter = ["status", "season", "matchday"]
    search_fields = ["home_team__name", "away_team__name"]
    raw_id_fields = ["home_team", "away_team"]


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = ["position", "team", "played", "won", "drawn", "lost", "goal_difference", "points", "season"]
    list_filter = ["season"]
    search_fields = ["team__name"]
