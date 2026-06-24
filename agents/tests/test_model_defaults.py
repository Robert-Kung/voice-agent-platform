"""Read-only model-defaults endpoint + source-of-truth parity (profile-editor-stack-ux).

The endpoint adds no runtime behavior — these tests assert it faithfully reflects
the authoritative constants and that the realtime variant allowlist stays in sync
with the cost rate table (so the UI never offers a variant the runtime rejects or
misprices).
"""

import asyncio
import json
import os
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
    # Catalog structure parity (provider/model lists; priced flag is computed,
    # not mirrored — checked in test_priced_flag_is_consistent).
    assert cat["direct_buildable"] == mirror["direct_buildable"]
    for kind in ("llm", "stt", "tts"):
        got_struct = {
            p: [e["model"] for e in entries]
            for p, entries in cat["pipeline"]["catalog"][kind].items()
        }
        assert got_struct == mirror["pipeline"]["catalog"][kind], f"{kind} catalog drift"
    assert cat["pipeline"]["voices"] == mirror["pipeline"]["voices"]


def test_priced_flag_is_consistent():
    """LLM priced flag = EXACT rate-key membership (model-granular); STT/TTS =
    provider membership (provider-granular, design D7). Exact, NOT the fuzzy cost
    matcher: a shorter key (gpt-4.1) must not falsely flag a distinct model
    (gpt-4.1-nano) as priced (review F-nano)."""
    from db.cost import LLM_RATES, STT_RATES, TTS_RATES, _match_llm_rate

    cat = build_model_catalog()["pipeline"]["catalog"]
    for provider, entries in cat["llm"].items():
        for e in entries:
            key = f"{provider}/{e['model']}"
            assert e["priced"] == (key in LLM_RATES), f"llm priced drift: {key}"
            # Cross-rate guard: a priced model must resolve to ITS OWN rate, never
            # a different model's via substring fuzz.
            if e["priced"]:
                assert _match_llm_rate(key) == LLM_RATES[key], f"llm cross-rate: {key}"
    for provider, entries in cat["stt"].items():
        for e in entries:
            assert e["priced"] == (provider in STT_RATES), f"stt priced drift: {provider}/{e}"
    for provider, entries in cat["tts"].items():
        for e in entries:
            assert e["priced"] == (provider in TTS_RATES), f"tts priced drift: {provider}/{e}"


def test_review4_newly_offered_providers_are_priced():
    """review #4: providers added to the catalog (cartesia STT; deepgram/rime/inworld
    TTS) now carry a cost rate so a session using them is not estimated at $0. (D7
    still permits unpriced-but-flagged providers in general; this only locks the ones
    we have authoritative LiveKit rates for.)"""
    from db.cost import STT_RATES, TTS_RATES

    assert "cartesia" in STT_RATES
    for provider in ("deepgram", "rime", "inworld"):
        assert provider in TTS_RATES, f"TTS provider {provider} offered but unpriced"


def test_direct_buildable_matches_runtime():
    """The DIRECT_BUILDABLE matrix (save-time validator source) must equal what
    providers.build_* can actually build, or a profile passes save then crashes at
    session start with no SIP fallback (review M3). Asserts the two never desync."""
    from runtime.constants import DIRECT_BUILDABLE, SpecError, normalize_spec
    from runtime import providers

    # Every declared-buildable (kind, provider) must NOT raise at normalize, and a
    # via:direct combo outside the matrix MUST raise.
    for kind, provider in DIRECT_BUILDABLE:
        spec = normalize_spec(kind, {"provider": provider, "model": "x", "via": "direct"})
        assert spec["via"] == "direct"
    with pytest.raises(SpecError):
        normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3", "via": "direct"})
    with pytest.raises(SpecError):
        normalize_spec("llm", {"provider": "openai", "model": "gpt-4o", "via": "direct"})
    # providers.py dispatch side: the llm-google-direct branch and stt-deepgram-direct
    # branch exist; assert the build functions reference exactly these.
    assert ("llm", "google") in DIRECT_BUILDABLE
    assert ("stt", "deepgram") in DIRECT_BUILDABLE


def _catalog_ids():
    """Flat [(kind, 'provider/model'), ...] over the whole catalog, for probe params."""
    from runtime.constants import MODEL_CATALOG

    return [
        (kind, f"{provider}/{model}")
        for kind in ("llm", "stt", "tts")
        for provider, models in MODEL_CATALOG[kind].items()
        for model in models
    ]


async def _probe_gateway(kind: str, mid: str) -> None:
    """Make a minimal REAL inference call through the LiveKit Inference gateway and
    raise if the gateway rejects the model id. Construction alone does NO network I/O
    (it only stores the id), so a renamed/deprecated id is only caught by an actual
    call: LLM → /v1/chat/completions (404 'model definition'); STT/TTS → WS handshake
    + session.create ('model not found' / 'INVALID_*'). No room/job needed — we seed
    an http session context for the WS-based STT/TTS paths."""
    from livekit import rtc
    from livekit.agents import inference
    from livekit.agents.llm import ChatContext
    from livekit.agents.types import APIConnectOptions
    from livekit.agents.utils import http_context

    fast = APIConnectOptions(max_retry=0, timeout=20.0)
    http_context._new_session_ctx()  # STT/TTS WS paths require an http session ctx
    try:
        if kind == "llm":
            comp = inference.LLM(model=mid)
            try:
                ctx = ChatContext.empty()
                ctx.add_message(role="user", content="hi")
                async with comp.chat(chat_ctx=ctx, conn_options=fast) as stream:
                    async for _ in stream:
                        break
            finally:
                await comp.aclose()
        elif kind == "tts":
            comp = inference.TTS(model=mid)
            try:
                async with comp.synthesize("hi", conn_options=fast) as stream:
                    async for _ in stream:
                        break
            finally:
                await comp.aclose()
        elif kind == "stt":
            comp = inference.STT(model=mid)
            try:
                stream = comp.stream(conn_options=fast)
                n = 3200  # 200ms silence @ 16k mono — enough to open the session
                stream.push_frame(
                    rtc.AudioFrame(
                        data=bytes(2 * n), sample_rate=16000, num_channels=1,
                        samples_per_channel=n,
                    )
                )
                stream.end_input()

                async def _drain():
                    async for _ in stream:
                        break

                # A rejected id raises APIError ("model not found") at session.create,
                # fast — that propagates out of _drain and fails the test. Silence may
                # legitimately yield no transcript event, so a timeout WITHOUT a
                # rejection means the gateway accepted the id (not a failure).
                try:
                    await asyncio.wait_for(_drain(), timeout=15)
                except asyncio.TimeoutError:
                    pass
                await stream.aclose()
            finally:
                await comp.aclose()
    finally:
        await http_context._close_http_ctx()


@pytest.mark.skipif(
    not os.environ.get("LIVEKIT_INFERENCE_PROBE"),
    reason="network probe — set LIVEKIT_INFERENCE_PROBE=1 (+ LIVEKIT_* creds) to run in CI/pre-deploy",
)
@pytest.mark.parametrize("kind,mid", _catalog_ids(), ids=lambda v: v)
def test_catalog_id_accepted_by_gateway(kind, mid):
    """GATING backstop (review C1/task 7.3): a minimal REAL call per catalog id against
    the live gateway. A renamed/deprecated id fails HERE in CI, before it can 422 a live
    SIP call (which has no FallbackAdapter net). Opt-in via LIVEKIT_INFERENCE_PROBE so
    the default offline suite stays network-free."""
    asyncio.run(_probe_gateway(kind, mid))


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_endpoint_serves_catalog(client):
    res = client.get("/api/model-defaults")
    assert res.status_code == 200
    body = res.json()
    assert body["schema"] == 2
    assert "pipeline" in body and "realtime" in body
    assert set(body["pipeline"]["catalog"]) == {"llm", "stt", "tts"}
    assert "voices" in body["pipeline"]
    assert body["direct_buildable"] == ["llm:google", "stt:deepgram"]
