from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from betting.forms import CurrencyForm, DisplayNameForm
from betting.models import Badge, UserBadge, UserBalance, UserStats
from betting.services import get_public_identity, get_user_rank, mask_email
from website.forms import LoginForm, SignupForm
from website.models import SiteSettings
from website.theme import THEME_SESSION_KEY, get_theme, normalize_theme

ARCHITECTURE_COMPONENTS = {
    "browser": {
        "label": "Browser",
        "subtitle": "Django Templates + HTMX + WebSocket",
        "description": "Pages are served as full HTML from Django templates. HTMX handles partial page updates, form submissions, and auto-polling — all without a JavaScript framework. The htmx-ext-ws extension connects to Django Channels for live score updates over WebSocket.",
        "tech": ["Django Templates", "HTMX 2.0", "htmx-ext-ws", "Tailwind CSS"],
        "pages": ["Dashboard (live scores via WS)", "Fixtures (matchday tabs via hx-get)", "Odds Board (30s polling)", "Match Detail (odds + bet form)", "My Bets (bet history)"],
    },
    "django": {
        "label": "Django",
        "subtitle": "Views, Models, ORM, Admin",
        "description": "The core application server. Django handles HTTP routing, renders templates, manages the ORM and migrations, and provides the admin interface. Views serve both full pages and HTMX partials depending on the request.",
        "tech": ["Django 5.x", "Gunicorn", "Django ORM", "Admin Site"],
        "pages": ["6 models (Match, Team, Standing, Odds, BetSlip, UserBalance)", "Class-based views for all pages", "HTMX-aware partial responses", "Full admin panel for data inspection"],
    },
    "channels": {
        "label": "Daphne / Channels",
        "subtitle": "ASGI + WebSocket Consumers",
        "description": "Daphne serves as the ASGI server, handling both HTTP and WebSocket connections. Django Channels provides WebSocket consumers that join channel groups per match, broadcasting score updates in real time as HTML partials.",
        "tech": ["Daphne (ASGI)", "Django Channels", "Channel Layers", "WebSocket Consumers"],
        "pages": ["DashboardConsumer — broadcasts all live match updates", "MatchConsumer — per-match score and status updates", "Out-of-band (OOB) HTML swaps for live DOM updates"],
    },
    "redis": {
        "label": "Redis",
        "subtitle": "Cache + Broker + Channel Layer",
        "description": "Redis plays three roles in one service: it caches API responses and computed data, acts as the Celery message broker for task queuing, and serves as the Django Channels layer backend for WebSocket pub/sub messaging.",
        "tech": ["Redis 7.x", "django-redis (cache)", "Celery broker", "channels-redis"],
        "pages": ["Cache: API responses, computed odds", "Broker: Celery task queue and results", "Channel Layer: WebSocket group messaging"],
    },
    "postgresql": {
        "label": "PostgreSQL",
        "subtitle": "Persistent Data Store",
        "description": "All application data lives in PostgreSQL. The Django ORM handles schema migrations, queries, and transactions. Atomic operations ensure bet placement deducts balances safely.",
        "tech": ["PostgreSQL 16", "Django ORM", "Migrations", "Atomic Transactions"],
        "pages": ["Match, Team, Standing — core football data", "Odds — bookmaker odds snapshots", "BetSlip, UserBalance — betting state", "Celery Beat schedule (django-celery-beat)"],
    },
    "celery": {
        "label": "Celery Worker",
        "subtitle": "Background Tasks + Periodic Jobs",
        "description": "Celery workers process background tasks: fetching fixtures and standings from football-data.org, pulling odds from The Odds API, and settling bets when matches finish. Celery Beat schedules periodic polling tasks.",
        "tech": ["Celery 5.x", "Celery Beat", "django-celery-beat", "httpx (async HTTP)"],
        "pages": ["fetch_fixtures — every 6 hours", "fetch_standings — every 6 hours", "fetch_odds — every 30 minutes", "fetch_live_scores — every 60s during matches", "settle_bets — triggered on match completion"],
    },
}

FLOW_PATHS = {
    "http": {
        "label": "HTTP Request",
        "description": "User clicks a link or HTMX fires a request. Django view processes it, queries PostgreSQL via ORM, renders a template (full page or partial), and returns HTML.",
        "steps": ["Browser", "Django", "PostgreSQL", "Django", "Browser"],
    },
    "websocket": {
        "label": "WebSocket",
        "description": "Browser opens a WebSocket to Daphne. When a Celery task detects a score change, it pushes a message through Redis channel layer. Daphne's consumer broadcasts the HTML update to all connected clients.",
        "steps": ["Browser", "Daphne/Channels", "Redis", "Daphne/Channels", "Browser"],
    },
    "celery": {
        "label": "Celery Task",
        "description": "Celery Beat triggers a periodic task. The worker fetches data from an external API, saves to PostgreSQL, and optionally pushes a WebSocket update through the Redis channel layer.",
        "steps": ["Celery Worker", "External API", "PostgreSQL", "Redis", "Daphne/Channels", "Browser"],
    },
}


class HomeView(TemplateView):
    template_name = "website/home.html"


class HowItWorksView(TemplateView):
    template_name = "website/how_it_works.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["components"] = ARCHITECTURE_COMPONENTS
        context["flows"] = FLOW_PATHS
        return context


class ComponentDetailView(View):
    def get(self, request):
        name = request.GET.get("name", "")
        component = ARCHITECTURE_COMPONENTS.get(name)
        if not component:
            raise Http404
        return render(request, "website/partials/component_detail.html", {
            "name": name,
            "component": component,
        })


class SignupView(View):
    def _registration_closed(self):
        site = SiteSettings.load()
        if site.max_users == 0:
            return False
        User = get_user_model()
        return User.objects.count() >= site.max_users

    def _closed_context(self):
        site = SiteSettings.load()
        return {
            "registration_closed": True,
            "closed_message": site.registration_closed_message,
        }

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("matches:dashboard")
        if self._registration_closed():
            return render(request, "website/signup.html", self._closed_context())
        return render(request, "website/signup.html", {"form": SignupForm()})

    def post(self, request):
        if self._registration_closed():
            return render(request, "website/signup.html", self._closed_context())

        form = SignupForm(request.POST)
        if not form.is_valid():
            return render(request, "website/signup.html", {"form": form})

        User = get_user_model()
        with transaction.atomic():
            site = SiteSettings.load_for_update()
            if site.max_users and User.objects.count() >= site.max_users:
                return render(request, "website/signup.html", self._closed_context())
            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            UserBalance.objects.create(user=user)
        login(request, user)
        return redirect("matches:dashboard")


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("matches:dashboard")
        return render(request, "website/login.html", {"form": LoginForm()})

    def post(self, request):
        form = LoginForm(request.POST)
        if not form.is_valid():
            return render(request, "website/login.html", {"form": form})

        user = authenticate(
            request,
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        if user is None:
            form.add_error(None, "Invalid email or password.")
            return render(request, "website/login.html", {"form": form})

        login(request, user)
        next_url = request.GET.get("next", "matches:dashboard")
        # Only redirect to URL names, not arbitrary paths
        return redirect(next_url if "/" in next_url else next_url)


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect("matches:dashboard")


class ThemeToggleView(View):
    def post(self, request):
        requested_theme = request.POST.get("theme")
        theme = normalize_theme(requested_theme)

        if requested_theme is None:
            theme = "light" if get_theme(request) == "dark" else "dark"

        request.session[THEME_SESSION_KEY] = theme

        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if not next_url or not url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = reverse("matches:dashboard")

        return redirect(next_url)


class AccountView(LoginRequiredMixin, View):
    def _partial_context(self, form, save_success=False):
        """Minimal context for HTMX partial responses — no extra DB queries."""
        user = self.request.user
        return {
            "display_name_form": form,
            "account_masked_email": mask_email(user.email),
            "account_public_identity": get_public_identity(user),
            "account_save_success": save_success,
        }

    def _build_context(self, form=None, save_success=False, currency_form=None, currency_save_success=False):
        user = self.request.user
        masked = mask_email(user.email)

        # Balance
        try:
            balance = user.balance.balance
        except UserBalance.DoesNotExist:
            balance = None

        # Stats
        try:
            stats = user.stats
        except UserStats.DoesNotExist:
            stats = None

        # Badges
        earned_map = {
            ub.badge_id: ub.earned_at
            for ub in UserBadge.objects.filter(user=user).select_related("badge")
        }
        all_badges = []
        for badge in Badge.objects.all():
            badge.earned = earned_map.get(badge.pk)
            all_badges.append(badge)

        return {
            "display_name_form": form or DisplayNameForm(instance=user),
            "currency_form": currency_form or CurrencyForm(instance=user),
            "account_masked_email": masked,
            "account_public_identity": get_public_identity(user),
            "account_save_success": save_success,
            "currency_save_success": currency_save_success,
            "user_rank": get_user_rank(user),
            "balance": balance,
            "stats": stats,
            "all_badges": all_badges,
        }

    def get(self, request):
        return render(request, "website/account.html", self._build_context())

    def post(self, request):
        form = DisplayNameForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            fresh_form = DisplayNameForm(instance=request.user)
            if request.htmx:
                return render(
                    request,
                    "website/partials/account_settings_card.html",
                    self._partial_context(fresh_form, save_success=True),
                )
            return render(request, "website/account.html", self._build_context(fresh_form, save_success=True))

        if request.htmx:
            return render(
                request,
                "website/partials/account_settings_card.html",
                self._partial_context(form),
                status=422,
            )
        return render(request, "website/account.html", self._build_context(form=form), status=422)


class CurrencyUpdateView(LoginRequiredMixin, View):
    def post(self, request):
        form = CurrencyForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            fresh_form = CurrencyForm(instance=request.user)
            if request.htmx:
                return render(
                    request,
                    "website/partials/currency_settings_card.html",
                    {"currency_form": fresh_form, "currency_save_success": True},
                )
            return redirect("website:account")

        if request.htmx:
            return render(
                request,
                "website/partials/currency_settings_card.html",
                {"currency_form": form},
                status=422,
            )
        return redirect("website:account")
