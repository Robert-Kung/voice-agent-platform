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
