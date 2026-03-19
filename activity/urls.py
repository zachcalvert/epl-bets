from django.urls import path

from . import views

app_name = "activity"

urlpatterns = [
    path("toggle-toasts/", views.toggle_toasts, name="toggle_toasts"),
]
