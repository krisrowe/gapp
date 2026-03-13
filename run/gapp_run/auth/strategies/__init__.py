"""Credential strategies for upstream token resolution."""

from gapp_run.auth.strategies.bearer import get_access_token as bearer_get_access_token
from gapp_run.auth.strategies.google_oauth2 import (
    get_access_token as google_oauth2_get_access_token,
)

STRATEGIES = {
    "bearer": bearer_get_access_token,
    "google_oauth2": google_oauth2_get_access_token,
}


def resolve_strategy(name: str):
    """Return the strategy function for the given name."""
    strategy = STRATEGIES.get(name)
    if not strategy:
        raise ValueError(f"Unknown credential strategy: {name!r}")
    return strategy
