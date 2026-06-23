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

    def test_direct_llm_nongoogle_fails_loud(self):
        # direct LLM is wired ONLY for google (+ deepgram STT); any other direct LLM
        # provider still fails loud at build (no silent fallback).
        with pytest.raises(SpecError):
            providers.build_llm([{"kind": "llm", "provider": "openai", "model": "x", "via": "direct", "options": {}}])

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
        assert r.model_names["schema"] == 1
        assert r.model_names["stt"] == [{"model": "deepgram/nova-2"}]
        assert r.model_names["realtime"][0]["model"]


# ── regression: no models block == pre-change defaults ─────
class TestDefaultBackfill:
    def test_pipeline_defaults_match_pre_change(self):
        r = providers.resolve_session_components({}, "pipeline")
        assert r.mode == "pipeline"
        assert isinstance(r.llm, lk_llm.FallbackAdapter)
        assert isinstance(r.stt, lk_stt.FallbackAdapter)
        assert isinstance(r.tts, lk_tts.FallbackAdapter)
        # primary model names equal the old hard-coded first entries
        assert r.model_names["schema"] == 1
        assert r.model_names["llm"] == [{"model": "google/gemini-3.1-flash-lite"}]
        assert r.model_names["stt"] == [{"model": "elevenlabs/scribe_v2_realtime"}]
        assert r.model_names["tts"][0]["model"].startswith("cartesia/sonic-3")

    def test_partial_block_backfills_missing(self):
        # declare only llm → declared LLM used; stt/tts fall back to defaults
        r = providers.resolve_session_components(
            {"models": {"llm": [{"provider": "google", "model": "gemini-2.5-flash"}]}},
            "pipeline",
        )
        assert r.model_names["llm"] == [{"model": "google/gemini-2.5-flash"}]
        assert isinstance(r.llm, lk_llm.LLM) and not isinstance(r.llm, lk_llm.FallbackAdapter)
        # backfilled defaults:
        assert r.model_names["stt"] == [{"model": "elevenlabs/scribe_v2_realtime"}]
        assert r.model_names["tts"][0]["model"].startswith("cartesia/sonic-3")


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


class TestCodeReviewFixes:
    """Regression tests for code-review findings on commit 8b78bd1."""

    def test_p1a_nondirect_stt_override_does_not_crash(self, monkeypatch):
        # AGENT_STT_PROVIDER set to a non-direct/typo value must NOT flip a default
        # STT spec to direct (which would SpecError and kill session start).
        monkeypatch.setenv("AGENT_STT_PROVIDER", "elevenlabs")
        r = providers.resolve_session_components({}, "pipeline")  # must not raise
        assert isinstance(r.stt, lk_stt.FallbackAdapter)

    def test_p1a_typo_override_is_noop(self, monkeypatch):
        monkeypatch.setenv("AGENT_STT_PROVIDER", "deepgrammm")
        spec = normalize_spec("stt", {"provider": "deepgram", "model": "nova-2", "via": "inference"})
        comp = providers.build_stt([providers._apply_stt_override(spec)])
        assert "inference" in type(comp).__module__  # not flipped to direct

    def test_p2a_direct_llm_nongoogle_rejected_at_validation(self):
        # google-direct LLM is now wired (accepted); a non-google direct LLM is not.
        with pytest.raises(SpecError):
            normalize_spec("llm", {"provider": "openai", "model": "x", "via": "direct"})
        assert normalize_spec("llm", {"provider": "google", "model": "x", "via": "direct"})["via"] == "direct"

    def test_p2a_direct_tts_rejected_at_validation(self):
        with pytest.raises(SpecError):
            normalize_spec("tts", {"provider": "deepgram", "model": "x", "via": "direct"})

    def test_p2a_direct_stt_nondeepgram_rejected(self):
        with pytest.raises(SpecError):
            normalize_spec("stt", {"provider": "google", "model": "x", "via": "direct"})

    def test_p2a_direct_stt_deepgram_ok(self):
        assert normalize_spec("stt", {"provider": "deepgram", "model": "nova-2", "via": "direct"})["via"] == "direct"

    def test_p2b_reserved_option_keys_rejected(self):
        for bad in ({"language": "zh"}, {"model": "x"}, {"provider": "y"}):
            with pytest.raises(SpecError):
                normalize_spec("stt", {"provider": "deepgram", "model": "nova-2", "options": bad})

    def test_p2b_normal_options_allowed(self):
        spec = normalize_spec("llm", {"provider": "google", "model": "x", "options": {"temperature": 0.5}})
        assert spec["options"] == {"temperature": 0.5}

    def test_p2c_garbage_mode_falls_back_to_default(self, monkeypatch):
        from agent import _resolve_mode, _DEFAULT_MODE
        monkeypatch.setenv("AGENT_MODE", "pipelime")
        assert _resolve_mode({}) == _DEFAULT_MODE


# ── profile-model-catalog-runtime: voice passthrough, google-direct, preflight ──
class TestVoicePassthrough:
    def test_voice_carried_through_normalize(self):
        spec = normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3", "voice": "9626"})
        assert spec["voice"] == "9626"

    def test_absent_voice_not_in_spec(self):
        spec = normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3"})
        assert "voice" not in spec

    def test_non_string_voice_rejected(self):
        with pytest.raises(SpecError):
            normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3", "voice": 123})

    def test_voice_is_reserved_option_key(self):
        with pytest.raises(SpecError):
            normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3", "options": {"voice": "x"}})

    def test_build_passes_voice_kwarg(self, monkeypatch):
        captured = {}
        def fake_tts(**kw):
            captured.update(kw)
            return object()
        monkeypatch.setattr(providers.inference, "TTS", fake_tts)
        providers._build_one_tts(normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3", "voice": "abc"}))
        assert captured["voice"] == "abc"
        assert captured["model"] == "cartesia/sonic-3"

    def test_build_omits_voice_when_absent(self, monkeypatch):
        captured = {}
        def fake_tts(**kw):
            captured.update(kw)
            return object()
        monkeypatch.setattr(providers.inference, "TTS", fake_tts)
        providers._build_one_tts(normalize_spec("tts", {"provider": "cartesia", "model": "sonic-3"}))
        assert "voice" not in captured


class TestGoogleDirectLLM:
    def test_validator_accepts_google_direct_llm(self):
        spec = normalize_spec("llm", {"provider": "google", "model": "gemini-2.5-flash", "via": "direct"})
        assert spec["via"] == "direct"

    def test_validator_rejects_openai_direct_llm(self):
        with pytest.raises(SpecError):
            normalize_spec("llm", {"provider": "openai", "model": "gpt-4o", "via": "direct"})

    def test_build_uses_bare_model_name(self, monkeypatch):
        captured = {}
        def fake_google_llm(**kw):
            captured.update(kw)
            return object()
        monkeypatch.setattr(providers.google, "LLM", fake_google_llm)
        providers._build_one_llm(normalize_spec("llm", {"provider": "google", "model": "gemini-2.5-flash", "via": "direct"}))
        # google.LLM takes a BARE model name, NOT provider/model
        assert captured["model"] == "gemini-2.5-flash"

    def test_inference_llm_uses_prefixed_name(self, monkeypatch):
        captured = {}
        def fake_inf_llm(**kw):
            captured.update(kw)
            return object()
        monkeypatch.setattr(providers.inference, "LLM", fake_inf_llm)
        providers._build_one_llm(normalize_spec("llm", {"provider": "google", "model": "gemini-2.5-flash"}))
        assert captured["model"] == "google/gemini-2.5-flash"


class TestPipelinePreflight:
    def test_failed_build_falls_back_to_defaults(self, monkeypatch):
        # A pinned llm spec whose build raises must degrade to the default chain,
        # and model_names must reflect the fallback, not the dead pin.
        real_build_llm = providers.build_llm
        calls = {"n": 0}
        def flaky_build_llm(specs):
            calls["n"] += 1
            if calls["n"] == 1:  # first call = the pinned spec
                raise RuntimeError("stale model id")
            return real_build_llm(specs)
        monkeypatch.setattr(providers, "build_llm", flaky_build_llm)
        profile = {"models": {"mode": "pipeline", "llm": {"provider": "google", "model": "dead-model"}}}
        resolved = providers.resolve_session_components(profile, "pipeline")
        names = [s["model"] for s in resolved.model_names["llm"]]
        assert "google/dead-model" not in names
        assert names  # fell back to a real default

    def test_default_chain_failure_reraises(self, monkeypatch):
        # If the DEFAULT chain itself can't build (platform misconfig, e.g. no
        # LIVEKIT_API_KEY), preflight must fail loud — NOT mask it into a None
        # component that crashes downstream (review P2).
        def always_fail(specs):
            raise RuntimeError("platform misconfigured")
        monkeypatch.setattr(providers, "build_llm", always_fail)
        profile = {"models": {"mode": "pipeline", "llm": {"provider": "google", "model": "dead-model"}}}
        with pytest.raises(RuntimeError, match="platform misconfigured"):
            providers.resolve_session_components(profile, "pipeline")
