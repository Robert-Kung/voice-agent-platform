"""Read-only model-defaults endpoint + source-of-truth parity (profile-editor-stack-ux).

The endpoint adds no runtime behavior — these tests assert it faithfully reflects
the authoritative constants and that the realtime variant allowlist stays in sync
with the cost rate table (so the UI never offers a variant the runtime rejects or
misprices).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes_model_defaults import build_model_catalog
from db.cost import _match_realtime_rate
from runtime.constants import (
    DEFAULT_PIPELINE_LLM,
    DEFAULT_REALTIME_MODEL,
    DEFAULT_REALTIME_VOICE,
    KNOWN_DIRECT_PROVIDERS,
    REALTIME_MODEL_ALLOWLIST,
)


def test_catalog_reflects_compiled_defaults():
    cat = build_model_catalog()
    assert cat["pipeline"]["defaults"]["llm"]["model"] == DEFAULT_PIPELINE_LLM[0]["model"]
    assert cat["realtime"]["defaults"]["model"] == DEFAULT_REALTIME_MODEL
    assert cat["realtime"]["defaults"]["voice"] == DEFAULT_REALTIME_VOICE
    assert cat["direct_providers"] == sorted(KNOWN_DIRECT_PROVIDERS)


def test_realtime_allowlist_matches_endpoint():
    cat = build_model_catalog()
    assert cat["realtime"]["model_allowlist"] == sorted(REALTIME_MODEL_ALLOWLIST)


def test_realtime_variants_are_priced():
    """Every offered realtime variant resolves to a NON-default cost rate, proving
    it's individually priced rather than silently falling back (cost-sync guard)."""
    cat = build_model_catalog()
    for variant in cat["realtime"]["model_allowlist"]:
        _, matched_key = _match_realtime_rate(variant)
        # The matched key must be a substring of the variant (a real match), not
        # the generic default fallback for an unknown name.
        assert matched_key.lower() in variant.lower(), (
            f"realtime variant {variant!r} has no dedicated cost rate"
        )


# NOTE: byte-for-byte default-resolution regression (the constant relocation from
# providers.py → constants.py) is covered by tests/test_runtime_providers.py
# TestDefaultBackfill, which sets the dummy provider keys needed to build
# components. Not duplicated here to keep this module import-light.


_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "lib"
    / "__fixtures__"
    / "backend-model-constants.json"
)


@pytest.mark.skipif(not _FIXTURE.exists(), reason="frontend fixture not present")
def test_catalog_matches_shared_frontend_fixture():
    """The shared JSON fixture is the single mirror checked from both languages.
    Backend changes must update it (this test), which then fails the vitest side —
    so the frontend fallback can't silently drift from the backend constants."""
    mirror = json.loads(_FIXTURE.read_text())
    cat = build_model_catalog()
    assert cat["direct_providers"] == mirror["direct_providers"]
    assert cat["realtime"]["llm_providers"] == mirror["realtime"]["llm_providers"]
    assert cat["realtime"]["model_allowlist"] == mirror["realtime"]["model_allowlist"]
    assert cat["realtime"]["defaults"]["model"] == mirror["realtime"]["defaults"]["model"]
    assert cat["realtime"]["defaults"]["voice"] == mirror["realtime"]["defaults"]["voice"]
    for kind in ("llm", "stt", "tts"):
        got = cat["pipeline"]["defaults"][kind]
        want = mirror["pipeline"]["defaults"][kind]
        assert got["provider"] == want["provider"]
        assert got["model"] == want["model"]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_endpoint_serves_catalog(client):
    res = client.get("/api/model-defaults")
    assert res.status_code == 200
    body = res.json()
    assert body["schema"] == 1
    assert "pipeline" in body and "realtime" in body
