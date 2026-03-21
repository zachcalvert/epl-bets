import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_seed_epl_command_runs_live_mode_and_generates_odds(monkeypatch, capsys):
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_teams", lambda season, offline=False: (20, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_matches", lambda season, offline=False: (380, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_standings", lambda season, offline=False: (20, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.generate_all_upcoming_odds", lambda season: [])

    call_command("seed_epl", season="2025")
    output = capsys.readouterr().out

    assert "Seeding EPL data (season=2025, mode=live)" in output
    assert "Generating house odds..." in output
    assert "Done!" in output


def test_seed_epl_command_skips_odds_with_flag(monkeypatch, capsys):
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_teams", lambda season, offline=False: (20, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_matches", lambda season, offline=False: (380, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_standings", lambda season, offline=False: (20, 0))

    call_command("seed_epl", season="2025", skip_odds=True)
    output = capsys.readouterr().out

    assert "Odds: skipped (--skip-odds)" in output


def test_seed_epl_command_skips_odds_in_offline_mode(monkeypatch, capsys):
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_teams", lambda season, offline=False: (20, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_matches", lambda season, offline=False: (380, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.sync_standings", lambda season, offline=False: (20, 0))
    monkeypatch.setattr("matches.management.commands.seed_epl.generate_all_upcoming_odds", lambda season: [])

    call_command("seed_epl", season="2025", offline=True)
    output = capsys.readouterr().out

    assert "mode=offline" in output
    assert "Generating house odds..." in output
