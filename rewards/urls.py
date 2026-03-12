from django.urls import path

from rewards import views

app_name = "rewards"

urlpatterns = [
    path(
        "rewards/<int:pk>/dismiss/",
        views.DismissRewardView.as_view(),
        name="dismiss",
    ),
]
