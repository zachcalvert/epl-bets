from django import template
from django.utils.safestring import mark_safe

register = template.Library()


STATUS_BADGE_MAP = {
    "SCHEDULED": ("gray", "text-gray-400 bg-gray-400/10", ""),
    "TIMED": ("gray", "text-gray-400 bg-gray-400/10", ""),
    "IN_PLAY": ("live", "text-accent bg-accent/10", "LIVE"),
    "PAUSED": ("live", "text-accent bg-accent/10", "HT"),
    "FINISHED": ("finished", "text-muted bg-muted/10", "FT"),
    "POSTPONED": ("postponed", "text-warning bg-warning/10", "PP"),
    "CANCELLED": ("cancelled", "text-danger bg-danger/10", "CAN"),
}


@register.simple_tag
def status_badge(match):
    status = match.status
    _, classes, label = STATUS_BADGE_MAP.get(status, ("gray", "text-gray-400 bg-gray-400/10", status))

    if status in ("SCHEDULED", "TIMED"):
        from django.utils import timezone
        local_kickoff = timezone.localtime(match.kickoff)
        label = local_kickoff.strftime("%a %H:%M")

    return mark_safe(
        f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {classes}">'
        f"{label}</span>"
    )


@register.simple_tag
def score_display(match):
    if match.home_score is not None and match.away_score is not None:
        return mark_safe(
            f'<span class="text-2xl font-bold font-mono">{match.home_score} - {match.away_score}</span>'
        )
    return mark_safe('<span class="text-lg text-muted">vs</span>')


@register.filter
def format_odds(value):
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return "-"
