from django.urls import path

from website.views import (
    AccountView,
    ComponentDetailView,
    CurrencyUpdateView,
    HowItWorksView,
    LoginView,
    LogoutView,
    SignupView,
    ThemeToggleView,
)

app_name = "website"

urlpatterns = [
    path("account/", AccountView.as_view(), name="account"),
    path("account/currency/", CurrencyUpdateView.as_view(), name="currency_update"),
    path("login/", LoginView.as_view(), name="login"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("theme/toggle/", ThemeToggleView.as_view(), name="theme_toggle"),
    path("how-it-works/", HowItWorksView.as_view(), name="how_it_works"),
    path("how-it-works/component/", ComponentDetailView.as_view(), name="component_detail"),
]
