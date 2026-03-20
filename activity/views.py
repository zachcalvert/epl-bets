from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_POST


@require_POST
@login_required
def toggle_toasts(request):
    """Toggle the user's activity toast preference."""
    user = request.user
    user.show_activity_toasts = "show_activity_toasts" in request.POST
    user.save(update_fields=["show_activity_toasts"])

    from website.views import _settings_card_context

    return render(
        request,
        "website/partials/account_settings_card.html",
        _settings_card_context(user),
    )
