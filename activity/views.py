from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST


@require_POST
@login_required
def toggle_toasts(request):
    """Toggle the user's activity toast preference."""
    user = request.user
    user.show_activity_toasts = "show_activity_toasts" in request.POST
    user.save(update_fields=["show_activity_toasts"])
    html = render_to_string(
        "activity/partials/activity_settings_card.html",
        {"user": user},
        request=request,
    )
    return HttpResponse(html)
