"""Tests for cost estimation (db/cost.py).

Regression coverage for the prefix-match bug: `google/gemini-2.5-flash` was
matching before `google/gemini-2.5-flash-lite` due to dict insertion order,
causing the wrong (more expensive) rate to be applied.
"""

from db.cost import compute_cost


class TestLLMCost:
    def test_exact_match_gemini_flash(self):
        r = compute_cost({
            "llm_model": "google/gemini-2.5-flash",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 0,
        })
        # 0.15 USD per 1M input tokens
        assert r["llm_usd"] == 0.15
        assert r["incomplete"] is False

    def test_lite_variant_prefers_longer_key(self):
        """Regression: gemini-2.5-flash-lite must NOT match gemini-2.5-flash.

        Expected: 0.075 USD/1M (lite rate), not 0.15 (flash rate).
        """
        r = compute_cost({
            "llm_model": "google/gemini-2.5-flash-lite",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 0,
        })
        assert r["llm_usd"] == 0.075
        assert r["incomplete"] is False

    def test_gpt_4o_mini_prefers_longer_key(self):
        """Regression: gpt-4o-mini must NOT match gpt-4o."""
        r = compute_cost({
            "llm_model": "openai/gpt-4o-mini",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 1_000_000,
        })
        # mini: 0.15 in + 0.60 out = 0.75 (not gpt-4o's 2.50 + 10.00 = 12.50)
        assert r["llm_usd"] == 0.75

    def test_gpt_4o_direct_match(self):
        r = compute_cost({
            "llm_model": "openai/gpt-4o",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 1_000_000,
        })
        assert r["llm_usd"] == 12.50

    def test_unknown_model_marks_incomplete(self):
        r = compute_cost({
            "llm_model": "anthropic/claude-3-opus",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 0,
        })
        assert r["llm_usd"] is None
        assert r["incomplete"] is True

    def test_zero_tokens_no_cost(self):
        r = compute_cost({
            "llm_model": "openai/gpt-4o-mini",
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
        })
        assert r["llm_usd"] is None
        assert r["total_usd"] is None


class TestTTSCost:
    def test_cartesia_tts(self):
        r = compute_cost({
            "tts_model": "cartesia/sonic",
            "tts_characters": 1500,  # 1500 / 150 = 10 min
        })
        # 10 min * 0.020 = 0.20
        assert abs(r["tts_usd"] - 0.20) < 1e-9

    def test_unknown_tts_incomplete(self):
        r = compute_cost({
            "tts_model": "mystery-tts",
            "tts_characters": 1500,
        })
        assert r["tts_usd"] is None
        assert r["incomplete"] is True


class TestSTTCost:
    def test_deepgram_stt(self):
        r = compute_cost({
            "stt_model": "deepgram/nova-2",
            "stt_audio_duration": 600,  # 10 min
        })
        # 10 min * 0.0043 = 0.043
        assert abs(r["stt_usd"] - 0.043) < 1e-9

    def test_elevenlabs_stt(self):
        r = compute_cost({
            "stt_model": "elevenlabs/scribe",
            "stt_audio_duration": 60,  # 1 min
        })
        assert abs(r["stt_usd"] - 0.010) < 1e-9


class TestTotalCost:
    def test_sums_all_components(self):
        r = compute_cost({
            "llm_model": "openai/gpt-4o-mini",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 0,
            "tts_model": "cartesia",
            "tts_characters": 150,  # 1 min → 0.020
            "stt_model": "deepgram",
            "stt_audio_duration": 60,  # 1 min → 0.0043
        })
        expected = 0.15 + 0.020 + 0.0043
        assert abs(r["total_usd"] - expected) < 1e-9
        assert r["incomplete"] is False

    def test_partial_data_incomplete_but_sums(self):
        r = compute_cost({
            "llm_model": "openai/gpt-4o-mini",
            "llm_prompt_tokens": 1_000_000,
            "llm_completion_tokens": 0,
            "tts_model": "mystery",
            "tts_characters": 150,  # no rate → marked incomplete
        })
        assert r["llm_usd"] == 0.15
        assert r["tts_usd"] is None
        assert r["total_usd"] == 0.15  # sum of known parts
        assert r["incomplete"] is True


class TestRealtimeCost:
    def test_realtime_explicit_mode(self):
        """Explicit agent_mode='realtime' uses Gemini Live audio rates."""
        r = compute_cost(
            {
                "llm_input_audio_tokens": 1_000_000,
                "llm_output_audio_tokens": 1_000_000,
                "llm_input_text_tokens": 0,
                "llm_output_text_tokens": 0,
            },
            agent_mode="realtime",
        )
        # 1M audio_in × $3 + 1M audio_out × $12 = $15
        assert r["mode"] == "realtime"
        assert r["llm_usd"] == 15.0
        assert r["total_usd"] == 15.0
        assert r["stt_usd"] is None  # no stt_audio_duration → no STT charge
        assert r["incomplete"] is False
        assert r["tokens"]["audio_in"] == 1_000_000

    def test_realtime_with_deepgram_stt(self):
        """Realtime architecture uses Deepgram STT — bill it alongside Gemini Live."""
        r = compute_cost(
            {
                "llm_input_text_tokens": 1_000_000,  # text-input pipeline
                "llm_output_audio_tokens": 1_000_000,
                "stt_audio_duration": 600,  # 10 min
            },
            agent_mode="realtime",
        )
        # LLM: 1M × 0.5 + 1M × 12 = $12.5
        # STT: 10 min × 0.0043 = $0.043
        assert abs(r["llm_usd"] - 12.5) < 1e-9
        assert abs(r["stt_usd"] - 0.043) < 1e-9
        assert abs(r["total_usd"] - 12.543) < 1e-9
        assert r["stt_provider"] == "deepgram/nova-2"

    def test_realtime_mixed_audio_text(self):
        r = compute_cost(
            {
                "llm_input_audio_tokens": 100,
                "llm_output_audio_tokens": 200,
                "llm_input_text_tokens": 1_000_000,
                "llm_output_text_tokens": 1_000_000,
            },
            agent_mode="realtime",
        )
        # 100 × 3 + 200 × 12 + 1M × 0.5 + 1M × 2 = 0.0003 + 0.0024 + 0.5 + 2 ≈ 2.5027
        assert abs(r["llm_usd"] - 2.5027) < 1e-4

    def test_realtime_cached_input_discount(self):
        r = compute_cost(
            {
                "llm_input_audio_tokens": 1_000_000,
                "llm_input_cached_audio_tokens": 1_000_000,  # all cached
                "llm_output_audio_tokens": 0,
            },
            agent_mode="realtime",
        )
        # billable audio_in = 0; cached = 1M × 0.075 = 0.075
        assert abs(r["llm_usd"] - 0.075) < 1e-9

    def test_auto_detect_realtime_via_audio_tokens(self):
        """No agent_mode given but audio tokens present → realtime path."""
        r = compute_cost({"llm_input_audio_tokens": 1_000_000})
        assert r["mode"] == "realtime"

    def test_pipeline_explicit_mode_skips_audio_path(self):
        """Explicit agent_mode='pipeline' forces pipeline path."""
        r = compute_cost(
            {"llm_input_audio_tokens": 1_000_000},  # would auto-detect as realtime
            agent_mode="pipeline",
        )
        assert r["mode"] == "pipeline"


class TestSelectedModelCost:
    """Cost driven by the resolver-selected model names (recorded on the session
    row), not the metrics-reported name. Critical because a fallback chain reports
    its model as the literal "FallbackAdapter" (fallback_adapter.py:80)."""

    def test_selected_prices_when_metrics_say_fallbackadapter(self):
        r = compute_cost(
            {"llm_model": "FallbackAdapter", "llm_prompt_tokens": 1_000_000, "llm_completion_tokens": 0},
            agent_mode="pipeline",
            selected={"llm": "google/gemini-3.1-flash-lite"},
        )
        assert r["llm_usd"] == 0.075
        assert r["incomplete"] is False

    def test_without_selected_fallbackadapter_is_incomplete(self):
        """Documents the bug being fixed: no selected name → unmatched → incomplete."""
        r = compute_cost(
            {"llm_model": "FallbackAdapter", "llm_prompt_tokens": 1_000_000, "llm_completion_tokens": 0},
            agent_mode="pipeline",
        )
        assert r["llm_usd"] is None
        assert r["incomplete"] is True

    def test_selected_stt_tts_priced(self):
        r = compute_cost(
            {
                "stt_model": "FallbackAdapter", "stt_audio_duration": 60,
                "tts_model": "FallbackAdapter", "tts_characters_count": 150,
            },
            agent_mode="pipeline",
            selected={"stt": "deepgram/nova-2", "tts": "cartesia/sonic-3"},
        )
        assert r["stt_usd"] is not None
        assert r["tts_usd"] is not None
        assert r["incomplete"] is False

    def test_realtime_stt_rate_from_stt_rates_table(self):
        """5.10: realtime STT rate resolves from STT_RATES by the selected provider,
        not a separate hard-coded constant."""
        from db.cost import STT_RATES
        r = compute_cost(
            {"llm_input_audio_tokens": 1_000_000, "stt_audio_duration": 600},
            agent_mode="realtime",
            selected={"realtime_model": "gemini-2.5-flash-native-audio-preview-12-2025", "realtime_stt": "deepgram/nova-2"},
        )
        assert r["stt_rate_per_min"] == STT_RATES["deepgram"]
        assert abs(r["stt_usd"] - (600 / 60.0) * STT_RATES["deepgram"]) < 1e-9
        assert r["stt_provider"] == "deepgram/nova-2"
