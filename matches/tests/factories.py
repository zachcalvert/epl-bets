from datetime import timedelta

import factory
from django.utils import timezone

from matches.models import Match, MatchStats, Standing, Team


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 1000 + n)
    name = factory.Sequence(lambda n: f"Team {n} FC")
    short_name = factory.Sequence(lambda n: f"Team {n}")
    tla = factory.Sequence(lambda n: f"T{n % 10}{(n + 1) % 10}")
    crest_url = factory.Sequence(lambda n: f"https://example.com/crest-{n}.png")
    venue = factory.Sequence(lambda n: f"Venue {n}")


class MatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Match

    external_id = factory.Sequence(lambda n: 2000 + n)
    home_team = factory.SubFactory(TeamFactory)
    away_team = factory.SubFactory(TeamFactory)
    home_score = None
    away_score = None
    status = Match.Status.SCHEDULED
    matchday = 1
    kickoff = factory.LazyFunction(lambda: timezone.now() + timedelta(days=1))
    season = "2025"


class MatchStatsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MatchStats

    match = factory.SubFactory(MatchFactory)
    h2h_json = factory.LazyFunction(list)
    h2h_summary_json = factory.LazyFunction(dict)
    home_form_json = factory.LazyFunction(list)
    away_form_json = factory.LazyFunction(list)
    fetched_at = factory.LazyFunction(timezone.now)


class StandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Standing

    team = factory.SubFactory(TeamFactory)
    season = "2025"
    position = factory.Sequence(lambda n: n + 1)
    played = 10
    won = 6
    drawn = 2
    lost = 2
    goals_for = 20
    goals_against = 10
    goal_difference = 10
    points = 20
