"""Tests for the model-provider runtime (runtime/constants.py + runtime/providers.py).

Covers:
  - spec parsing / normalization + default via=inference
  - build dispatch: single spec → bare component, multiple → FallbackAdapter
  - via: inference (gateway) vs direct (deepgram), and the AGENT_STT_PROVIDER override
  - realtime resolver: TextInputRealtimeModel built, non-Gemini provider rejected
  - regression: a profile WITHOUT a models block resolves to the pre-change defaults
  - partial backfill: declaring only `llm` leaves stt/tts on defaults
  - effective-mode precedence (_resolve_mode): AGENT_MODE env > models.mode > default

Component construction (inference.* / deepgram.*) validates key presence at build
time but does no network I/O, so dummy keys are enough.
"""

import os

os.environ.setdefault("LIVEKIT_API_KEY", "test")
os.environ.setdefault("LIVEKIT_API_SECRET", "test")
os.environ.setdefault("LIVEKIT_URL", "ws://test")
os.environ.setdefault("DEEPGRAM_API_KEY", "test")
os.environ.setdefault("GOOGLE_API_KEY", "test")

import pytest

from livekit.agents import llm as lk_llm, stt as lk_stt, tts as lk_tts

from runtime.constants import (
    DEFAULT_VIA,
    SpecError,
    normalize_spec,
    normalize_specs,
    validate_models_block,
)
from runtime import providers


# ── spec parsing ───────────────────────────────────────────
class TestSpecParsing:
    def test_default_via_is_inference(self):
        assert normalize_spec("llm", {"provider": "google", "model": "x"})["via"] == DEFAULT_VIA == "inference"

    def test_missing_provider_or_model_raises(self):
        with pytest.raises(SpecError):
            normalize_spec("llm", {"model": "x"})
        with pytest.raises(SpecError):
            normalize_spec("llm", {"provider": "google"})

    def test_invalid_via_raises(self):
        with pytest.raises(SpecError):
            normalize_spec("stt", {"provider": "deepgram", "model": "nova-2", "via": "carrier-pigeon"})

    def test_direct_unknown_provider_rejected(self):
        with pytest.raises(SpecError):
            normalize_spec("stt", {"provider": "cartesia", "model": "x", "via": "direct"})

    def test_direct_known_provider_ok(self):
        spec = normalize_spec("stt", {"provider": "deepgram", "model": "nova-2", "via": "direct"})
        assert spec["via"] == "direct"

    def test_single_dict_normalized_to_list(self):
        assert len(normalize_specs("llm", {"provider": "google", "model": "x"})) == 1

    def test_none_normalizes_to_empty(self):
        assert normalize_specs("llm", None) == []


# ── build dispatch ─────────────────────────────────────────
class TestBuildDispatch:
    def test_single_spec_is_bare_component(self):
        comp = providers.build_llm(normalize_specs("llm", [{"provider": "google", "model": "gemini-2.5-flash"}]))
        assert isinstance(comp, lk_llm.LLM)
        assert not isinstance(comp, lk_llm.FallbackAdapter)

    def test_multiple_specs_become_fallback_adapter(self):
        comp = providers.build_llm(normalize_specs("llm", [
            {"provider": "google", "model": "gemini-3.1-flash-lite"},
            {"provider": "openai", "model": "gpt-4.1-mini"},
        ]))
        assert isinstance(comp, lk_llm.FallbackAdapter)

    def test_direct_llm_fails_loud(self):
        # direct is only wired for deepgram STT + google realtime; direct LLM rejected
        with pytest.raises(SpecError):
            providers.build_llm([{"kind": "llm", "provider": "google", "model": "x", "via": "direct", "options": {}}])

    def test_tts_single_and_multi(self):
        single = providers.build_tts(normalize_specs("tts", [{"provider": "cartesia", "model": "sonic-3"}]))
        assert isinstance(single, lk_tts.TTS) and not isinstance(single, lk_tts.FallbackAdapter)
        multi = providers.build_tts(normalize_specs("tts", [
            {"provider": "cartesia", "model": "sonic-3"},
            {"provider": "elevenlabs", "model": "eleven_multilingual_v2"},
        ]))
        assert isinstance(multi, lk_tts.FallbackAdapter)


# ── via selection + AGENT_STT_PROVIDER override ────────────
class TestSTTViaAndOverride:
    def test_inference_via_builds_inference_stt(self):
        comp = providers.build_stt(normalize_specs("stt", [{"provider": "deepgram", "model": "nova-2", "via": "inference"}]))
        assert "inference" in type(comp).__module__

    def test_direct_via_builds_deepgram_plugin(self):
        comp = providers.build_stt(normalize_specs("stt", [{"provider": "deepgram", "model": "nova-2", "via": "direct"}]))
        assert "deepgram" in type(comp).__module__

    def test_agent_stt_provider_override_forces_direct(self, monkeypatch):
        # spec says via:inference, but the global override flips deepgram → direct
        monkeypatch.setenv("AGENT_STT_PROVIDER", "deepgram")
        comp = providers.build_stt(normalize_specs("stt", [{"provider": "deepgram", "model": "nova-2", "via": "inference"}]))
        assert "deepgram" in type(comp).__module__

    def test_override_does_not_touch_other_providers(self, monkeypatch):
        monkeypatch.setenv("AGENT_STT_PROVIDER", "deepgram")
        comp = providers.build_stt(normalize_specs("stt", [{"provider": "elevenlabs", "model": "scribe_v2_realtime", "via": "inference"}]))
        assert "inference" in type(comp).__module__


# ── realtime resolver ──────────────────────────────────────
class TestRealtimeResolver:
    def test_builds_text_input_realtime_model(self):
        rt_llm, model, voice = providers.build_realtime_llm({"voice": "Puck"})
        assert isinstance(rt_llm, providers.TextInputRealtimeModel)
        assert voice == "Puck"

    def test_non_gemini_provider_rejected(self):
        with pytest.raises(SpecError):
            providers.build_realtime_llm({"provider": "openai", "model": "gpt-realtime"})

    def test_resolver_realtime_returns_realtime_llm_and_stt(self):
        r = providers.resolve_session_components({}, "realtime")
        assert r.mode == "realtime"
        assert isinstance(r.llm, providers.TextInputRealtimeModel)
        assert r.tts is None
        assert r.model_names["realtime_stt"] == "deepgram/nova-2"


# ── regression: no models block == pre-change defaults ─────
class TestDefaultBackfill:
    def test_pipeline_defaults_match_pre_change(self):
        r = providers.resolve_session_components({}, "pipeline")
        assert r.mode == "pipeline"
        assert isinstance(r.llm, lk_llm.FallbackAdapter)
        assert isinstance(r.stt, lk_stt.FallbackAdapter)
        assert isinstance(r.tts, lk_tts.FallbackAdapter)
        # primary model names equal the old hard-coded first entries
        assert r.model_names["llm"] == "google/gemini-3.1-flash-lite"
        assert r.model_names["stt"] == "elevenlabs/scribe_v2_realtime"
        assert r.model_names["tts"].startswith("cartesia/sonic-3")

    def test_partial_block_backfills_missing(self):
        # declare only llm → declared LLM used; stt/tts fall back to defaults
        r = providers.resolve_session_components(
            {"models": {"llm": [{"provider": "google", "model": "gemini-2.5-flash"}]}},
            "pipeline",
        )
        assert r.model_names["llm"] == "google/gemini-2.5-flash"
        assert isinstance(r.llm, lk_llm.LLM) and not isinstance(r.llm, lk_llm.FallbackAdapter)
        # backfilled defaults:
        assert r.model_names["stt"] == "elevenlabs/scribe_v2_realtime"
        assert r.model_names["tts"].startswith("cartesia/sonic-3")


# ── effective mode precedence ──────────────────────────────
class TestModePrecedence:
    def test_profile_mode_used_when_env_unset(self, monkeypatch):
        from agent import _resolve_mode
        monkeypatch.delenv("AGENT_MODE", raising=False)
        assert _resolve_mode({"models": {"mode": "pipeline"}}) == "pipeline"

    def test_env_overrides_profile_mode(self, monkeypatch):
        from agent import _resolve_mode
        monkeypatch.setenv("AGENT_MODE", "realtime")
        assert _resolve_mode({"models": {"mode": "pipeline"}}) == "realtime"

    def test_default_when_neither_set(self, monkeypatch):
        from agent import _resolve_mode, _DEFAULT_MODE
        monkeypatch.delenv("AGENT_MODE", raising=False)
        assert _resolve_mode({}) == _DEFAULT_MODE


# ── models-block validation (shape only) ───────────────────
class TestModelsBlockValidation:
    def test_valid_block_passes(self):
        validate_models_block({"mode": "pipeline", "llm": [{"provider": "google", "model": "x"}]})

    def test_bad_mode_rejected(self):
        with pytest.raises(SpecError):
            validate_models_block({"mode": "banana"})

    def test_realtime_dead_variant_rejected(self):
        with pytest.raises(SpecError):
            validate_models_block({"realtime": {"model": "gemini-3.1-flash-live-preview"}})
