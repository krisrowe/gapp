"""Tests for strategy resolution."""

import pytest

from gapp_run.auth.strategies import resolve_strategy
from gapp_run.auth.strategies.bearer import get_access_token as bearer_fn


class TestStrategyResolution:
    def test_resolves_bearer(self):
        assert resolve_strategy("bearer") is bearer_fn

    def test_resolves_google_oauth2(self):
        fn = resolve_strategy("google_oauth2")
        assert callable(fn)

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown credential strategy"):
            resolve_strategy("nonexistent")
