from flags.models import FeatureFlag


def is_flag_enabled(flag_name, user=None):
    """Return True if the named feature flag is active for *user*.

    Returns False when the flag does not exist, so callers never need to
    handle a missing-flag exception.

    Usage::

        from flags.helpers import is_flag_enabled

        if is_flag_enabled("enhanced-match-stats", request.user):
            ...
    """
    try:
        flag = FeatureFlag.objects.get(name=flag_name)
    except FeatureFlag.DoesNotExist:
        return False
    return flag.is_enabled(user=user)
