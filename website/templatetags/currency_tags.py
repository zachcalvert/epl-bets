from django import template

register = template.Library()

CURRENCY_CONFIG = {
    "USD": {"symbol": "$"},
    "GBP": {"symbol": "£"},
    "EUR": {"symbol": "€"},
}


def format_currency(value, currency_code="GBP"):
    """Format a numeric value with the given currency symbol. Usable from Python code."""
    config = CURRENCY_CONFIG.get(currency_code, CURRENCY_CONFIG["GBP"])
    return f"{config['symbol']}{float(value):,.2f}"


def get_currency_symbol(user):
    """Get the currency symbol for a user."""
    code = getattr(user, "currency", "GBP") if user else "GBP"
    return CURRENCY_CONFIG.get(code, CURRENCY_CONFIG["GBP"])["symbol"]


@register.filter
def currency(value, user):
    """Usage: {{ amount|currency:user }}"""
    if value is None:
        return ""
    code = getattr(user, "currency", "GBP") if user else "GBP"
    return format_currency(value, code)


@register.simple_tag
def currency_symbol(user):
    """Returns just the symbol: £, $, €"""
    return get_currency_symbol(user)
