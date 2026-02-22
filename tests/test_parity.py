"""Tests for sync/async parity across all client pairs.

Verifies that every sync class and its async counterpart expose the same
public methods with identical parameter signatures.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

SYNC_ASYNC_PAIRS = [
    ("gofetch.client", "GoFetchClient", "AsyncGoFetchClient"),
    ("gofetch.actor", "ActorClient", "AsyncActorClient"),
    ("gofetch.dataset", "DatasetClient", "AsyncDatasetClient"),
    ("gofetch.run", "RunClient", "AsyncRunClient"),
    ("gofetch.webhook_client", "WebhookClient", "AsyncWebhookClient"),
    ("gofetch.webhook_client", "WebhookCollectionClient", "AsyncWebhookCollectionClient"),
    ("gofetch.log", "LogClient", "AsyncLogClient"),
]


@pytest.mark.parametrize(
    "module_name,sync_name,async_name",
    SYNC_ASYNC_PAIRS,
    ids=[f"{s}|{a}" for _, s, a in SYNC_ASYNC_PAIRS],
)
def test_method_names_match(
    module_name: str,
    sync_name: str,
    async_name: str,
) -> None:
    """Verify sync and async class pairs expose the same public method names."""
    mod = importlib.import_module(module_name)
    sync_cls = getattr(mod, sync_name)
    async_cls = getattr(mod, async_name)

    sync_methods = {
        name
        for name in dir(sync_cls)
        if not name.startswith("_") and callable(getattr(sync_cls, name))
    }
    async_methods = {
        name
        for name in dir(async_cls)
        if not name.startswith("_") and callable(getattr(async_cls, name))
    }

    assert sync_methods == async_methods, (
        f"{sync_name} and {async_name} have different public methods. "
        f"Only in sync: {sync_methods - async_methods}. "
        f"Only in async: {async_methods - sync_methods}."
    )


@pytest.mark.parametrize(
    "module_name,sync_name,async_name",
    SYNC_ASYNC_PAIRS,
    ids=[f"{s}|{a}" for _, s, a in SYNC_ASYNC_PAIRS],
)
def test_method_signatures_match(
    module_name: str,
    sync_name: str,
    async_name: str,
) -> None:
    """Verify sync and async class pairs have matching parameter lists for every public method."""
    mod = importlib.import_module(module_name)
    sync_cls = getattr(mod, sync_name)
    async_cls = getattr(mod, async_name)

    sync_methods = {
        name
        for name in dir(sync_cls)
        if not name.startswith("_") and callable(getattr(sync_cls, name))
    }

    for method_name in sorted(sync_methods):
        sync_sig = inspect.signature(getattr(sync_cls, method_name))
        async_sig = inspect.signature(getattr(async_cls, method_name))
        sync_params = list(sync_sig.parameters.keys())
        async_params = list(async_sig.parameters.keys())
        assert sync_params == async_params, (
            f"{sync_name}.{method_name}{sync_sig} != "
            f"{async_name}.{method_name}{async_sig}"
        )
