from django.contrib import admin

from betting.models import BetSlip, Odds, UserBalance


@admin.register(Odds)
class OddsAdmin(admin.ModelAdmin):
    list_display = ["match", "bookmaker", "home_win", "draw", "away_win", "fetched_at"]
    list_filter = ["bookmaker"]
    search_fields = ["match__home_team__name", "match__away_team__name"]
    raw_id_fields = ["match"]


@admin.register(BetSlip)
class BetSlipAdmin(admin.ModelAdmin):
    list_display = ["user", "match", "selection", "odds_at_placement", "stake", "status", "payout"]
    list_filter = ["status", "selection"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "match"]


@admin.register(UserBalance)
class UserBalanceAdmin(admin.ModelAdmin):
    list_display = ["user", "balance"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
