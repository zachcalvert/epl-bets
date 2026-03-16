"""Bot registry — maps bot accounts to their strategy classes."""

from bots.strategies import (
    ChaosAgentStrategy,
    DrawSpecialistStrategy,
    FrontrunnerStrategy,
    HomerBotStrategy,
    ParlayStrategy,
    UnderdogStrategy,
    ValueHunterStrategy,
)

BOT_PROFILES = [
    {
        "email": "frontrunner@bots.eplbets.local",
        "display_name": "The Frontrunner",
        "strategy": FrontrunnerStrategy,
    },
    {
        "email": "underdog@bots.eplbets.local",
        "display_name": "Underdog United",
        "strategy": UnderdogStrategy,
    },
    {
        "email": "parlaypete@bots.eplbets.local",
        "display_name": "Parlay Pete",
        "strategy": ParlayStrategy,
    },
    {
        "email": "drawdoctor@bots.eplbets.local",
        "display_name": "The Draw Doctor",
        "strategy": DrawSpecialistStrategy,
    },
    {
        "email": "valuehunter@bots.eplbets.local",
        "display_name": "Value Victor",
        "strategy": ValueHunterStrategy,
    },
    {
        "email": "chaoscharlie@bots.eplbets.local",
        "display_name": "Chaos Charlie",
        "strategy": ChaosAgentStrategy,
    },
]

# Lookup: email -> strategy class
STRATEGY_MAP = {p["email"]: p["strategy"] for p in BOT_PROFILES}


def get_strategy_for_bot(user):
    """Return an instantiated strategy for the given bot user, or None."""
    # Homer bots are configured via HomerBotConfig rather than the static map
    from bots.models import (
        HomerBotConfig,  # local import avoids circular at module level
    )

    try:
        config = user.homer_config
        return HomerBotStrategy(
            team_id=config.team_id,
            draw_underdog_threshold=config.draw_underdog_threshold,
        )
    except HomerBotConfig.DoesNotExist:
        pass

    cls = STRATEGY_MAP.get(user.email)
    return cls() if cls else None
