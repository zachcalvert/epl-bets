"""Bot registry — maps bot accounts to their strategy classes."""

from bots.strategies import (
    AllInAliceStrategy,
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
        "avatar_icon": "trophy",
        "avatar_bg": "#4f46e5",
    },
    {
        "email": "underdog@bots.eplbets.local",
        "display_name": "Underdog United",
        "strategy": UnderdogStrategy,
        "avatar_icon": "wolf",
        "avatar_bg": "#dc2626",
    },
    {
        "email": "parlaypete@bots.eplbets.local",
        "display_name": "Parlay Pete",
        "strategy": ParlayStrategy,
        "avatar_icon": "crown",
        "avatar_bg": "#d97706",
    },
    {
        "email": "drawdoctor@bots.eplbets.local",
        "display_name": "The Draw Doctor",
        "strategy": DrawSpecialistStrategy,
        "avatar_icon": "target",
        "avatar_bg": "#0891b2",
    },
    {
        "email": "valuehunter@bots.eplbets.local",
        "display_name": "Value Victor",
        "strategy": ValueHunterStrategy,
        "avatar_icon": "lightning",
        "avatar_bg": "#059669",
    },
    {
        "email": "chaoscharlie@bots.eplbets.local",
        "display_name": "Chaos Charlie",
        "strategy": ChaosAgentStrategy,
        "avatar_icon": "flame",
        "avatar_bg": "#ea580c",
    },
    {
        "email": "allinalice@bots.eplbets.local",
        "display_name": "All In Alice",
        "strategy": AllInAliceStrategy,
        "avatar_icon": "rocket",
        "avatar_bg": "#db2777",
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
