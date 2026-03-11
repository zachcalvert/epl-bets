from django.contrib.auth import authenticate, login, logout
from django.http import Http404
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from betting.models import UserBalance
from website.forms import LoginForm, SignupForm

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
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("matches:dashboard")
        return render(request, "website/signup.html", {"form": SignupForm()})

    def post(self, request):
        form = SignupForm(request.POST)
        if not form.is_valid():
            return render(request, "website/signup.html", {"form": form})

        from django.contrib.auth import get_user_model

        User = get_user_model()
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
