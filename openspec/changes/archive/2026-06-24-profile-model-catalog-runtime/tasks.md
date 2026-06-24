> Builds on archived `profile-editor-model-voice-ux`. Backend runtime changes ARE in scope this time. Gate: task 1.x (model-id verification) must complete before the catalog is committed — a wrong id has no fallback on a SIP call.

## 1. Verify the LiveKit Inference catalog against the live project (GATING)

- [x] 1.1 Verified via the installed `livekit-agents` 1.5.2 SDK accepted set (Literal types in `inference/{llm,stt,tts}.py`). Namespace truth: format is **`provider/model`** (our current form, NOT docs' bare `gemini/2.5-flash`); ElevenLabs STT is **`scribe_v2_realtime`** (underscore, our form is right). Full set recorded in `~/.gstack/.../-sdk-verification.md`. DECISION: seed from SDK 1.5.2 set + keep `google/gemini-3.1-flash-lite` as a known-good extra (current default, not regressed). No SDK upgrade (1.6.2 exists), no live-probe block — runtime preflight (7.2) + CI probe (7.3) are the backstops.
- [x] 1.2 Confirm whether `inference.TTS` accepts a `voice=` kwarg directly (vs via options) on the installed version; record the exact build call for `models.tts.voice`. **CONFIRMED (livekit-agents 1.5.2):** `inference.TTS(model, *, voice: NotGivenOr[str] = NOT_GIVEN, language, ...)` — `voice=` is a first-class kwarg. Build call: `inference.TTS(model=_model_id(spec), voice=spec["voice"], language=language, **spec["options"])` (omit `voice=` when absent).
- [x] 1.3 Collected from docs.livekit.io/agents/models/tts. Per-provider suggested voices (cartesia/deepgram/elevenlabs/rime/inworld) recorded with ids + human labels. LiveKit documents voices as `provider/model:voice-id`; the bare voice id (after `:`) is the value for the `voice=` kwarg. Our current default voice = cartesia Jacqueline (`9626c31c-...`).

## 2. Backend catalog + cost (source of truth)

- [x] 2.1 Add the verified catalog to import-light `runtime/constants.py`: enumerable provider/model lists per kind, per-provider suggested voices, and which providers have a direct build path. Only ids confirmed in 1.1 ship.
- [x] 2.2 Extend `api/routes_model_defaults.build_model_catalog()` to serve the full catalog + suggested voices + a per-model `priced` flag (rate exists in `db/cost.py`).
- [x] 2.3 Add `db/cost.py` rate entries for newly-offered priced models; align rate-table keys to the model-id strings the runtime actually accepts (from 1.1). Unpriced models stay offered (flagged), not removed.
- [x] 2.4 Update the shared `frontend/lib/__fixtures__/backend-model-constants.json` to mirror the expanded catalog core; keep the pytest parity test green.

## 3. Backend runtime build paths

- [x] 3.1 `runtime/providers.py` `_build_one_tts`: pass `models.tts.voice` through to the TTS component (per 1.2) when present; absent → current model-id-only behavior. No silent drop.
- [x] 3.2 `runtime/providers.py` `_build_one_llm`: add a Google direct-SDK build path (`provider: google, via: direct` → Google plugin + `GOOGLE_API_KEY`); other non-inference providers still fail loud.
- [x] 3.3 `runtime/constants.py` validator (`normalize_spec` / `validate_models_block`): accept `tts.voice` and the Google `via:direct` LLM combination; reject `via:direct` combos with no wired build path.
- [x] 3.4 pytest: voice passthrough applied at TTS build; Google direct LLM build path; validator accepts `tts.voice` + google-direct and rejects unbuildable direct; default-backfill regression still byte-for-byte.

## 4. Frontend catalog consumption + types

- [x] 4.1 Expand `frontend/lib/model-catalog.ts` types + `FALLBACK_MODEL_CATALOG`: full provider/model lists, suggested voices, `priced` flag, direct-capable providers. Keep it matching the shared fixture (vitest contract).
- [x] 4.2 `frontend/hooks/use-profile-form.ts`: read/write `models.tts.voice` (separate field) and per-spec `via`; round-trip + `pruneModels` handle the new field; `isDirty` covers them.

## 5. Frontend UI (StackSettings)

- [x] 5.1 Pipeline LLM/STT/TTS: provider dropdown + model dropdown sourced from the catalog (free-form remains as escape hatch for custom ids).
- [x] 5.2 Pipeline voice: separate `models.tts.voice` control — per-provider suggested-voice dropdown + free-form for custom/cloned ids; legacy model-id-encoded voice surfaced non-destructively.
- [x] 5.3 Per-spec `via:inference`/`via:direct` toggle shown only for direct-capable providers (Google); writes `via` and round-trips.
- [x] 5.4 Unpriced model flag: "cost estimate unavailable" badge at selection; never hide/block; speed/language controls hidden/disabled where unsupported.
- [x] 5.5 Preserve prior behavior: graph×realtime exclusivity (Realtime tab locked in graph), inherited/pinned distinction, deployment-env-override honesty.

## 6. Tests & verification

- [x] 6.1 vitest green: expanded catalog round-trip (incl. `models.tts.voice`, per-spec `via`), contract test vs shared fixture, unpriced-flag logic.
- [x] 6.2 `cd agents && uv run pytest tests/ -q` green: catalog/cost parity, voice passthrough, google-direct build + validation, default-backfill regression.
- [x] 6.3 frontend build passes.
- [x] 6.4 Browser QA: provider/model dropdowns from catalog; pipeline voice picker round-trips to `models.tts.voice` and the session applies it (Try ▶); Google `via:direct` toggle round-trips and runs; unpriced flag visible; graph×realtime still gated; legacy voice-in-model-id profile still loads/runs.
- [x] 6.5 `openspec validate profile-model-catalog-runtime --strict` passes.

## 7. Autoplan review must-fixes (fold into the sections above; listed here for traceability)

- [x] 7.1 (C3) `_build_one_llm` google-direct branch uses **bare** `spec["model"]` for `google.LLM`; `model_names` keeps `provider/model`; cost keys stay `provider/model`. pytest mocks `google.LLM` and asserts the bare model arg.
- [x] 7.2 (C1) Runtime preflight fallback: pipeline resolver degrades a failed-to-build pinned spec to a known-good safe chain + loud warning (no dropped call). pytest covers it.
- [x] 7.3 (C1) Network-gated pytest (`test_catalog_id_accepted_by_gateway`, opt-in via `LIVEKIT_INFERENCE_PROBE=1` + `LIVEKIT_*` creds; skips in the default offline suite) that makes a minimal REAL inference call per catalog id and asserts the gateway accepts it. NOT construction-only (that does no network I/O = the "theater" the review warned against): LLM → real `chat()` (404 on bad id); STT/TTS → real WS handshake + `session.create` ("model not found" / "INVALID_*"), no room/job needed (seeds `http_context._new_session_ctx()`). First real run caught **10/54 seeded ids rejected by the live gateway** — pruned from the catalog (gemini-3-pro, kimi-k2-instruct, deepseek-v3.2, deepgram flux-general*, all assemblyai STT, elevenlabs scribe_v2_realtime STT, deepgram/aura TTS); `scribe_v2_realtime` was also the primary `DEFAULT_PIPELINE_STT` → dropped, default now single `deepgram/nova-2`. Re-run confirms remaining catalog 100% accepted. CI wiring still TODO (operator must set `LIVEKIT_*` as CI secret).
- [x] 7.4 (C2/D6) Downgrade `profile-model-config` spec language to "validator guarantees shape, not runnability"; validator does NOT check model-id vs catalog (keeps free-form escape hatch).
- [x] 7.5 (H1/D7) Invert catalog↔cost dependency: `routes_model_defaults._llm_options()` stops deriving from `LLM_RATES`; catalog is authoritative, cost annotates `priced`. Assertion test: every catalog llm id → `_match_llm_rate ≠ None OR flagged unpriced`. Namespace flips atomically across cost/catalog/runtime/fixture.
- [x] 7.6 (D7) `priced` flag is model-granular for LLM, provider-granular for STT/TTS; UI badge + spec say so explicitly.
- [x] 7.7 (M1) Add `voice` to `normalize_spec` `reserved` options keys; pin-test `inference.TTS(voice=)` accepted on installed SDK.
- [x] 7.8 (M3) Replace the validator `else: raise` with `DIRECT_BUILDABLE = {("stt","deepgram"),("llm","google")}` in `constants.py`, consumed by `normalize_spec` and asserted against `providers.build_*`. Keep `tts via:direct` rejected.
- [x] 7.9 (H2) `specHasValue`/`pruneModels` treat `voice` as meaningful; vitest round-trip `{ tts: { voice: 'x' } }` survives prune.
- [x] 7.10 (D8/C2) Provider-change resets model+voice (no surviving invalid combo); vitest covers it.
- [x] 7.11 (D8) Stacked TTS control layout; via-toggle human labels; unpriced badge below field; cost chip reads "incomplete" for unpriced; legacy `provider/model:<voice>` detection + non-destructive pre-fill; empty-voice-list → free-text degrade.
- [x] 7.12 (M4) Release/runbook note: rollback requires reverting pinned google-`via:direct` pipeline profiles first (old code rejects them; SIP has no fallback).
- [x] 7.13 Speed/language controls: orphan requirement (no per-provider capability data, not in current UI). Either cut from this change or add a catalog capability-matrix task + control task — do NOT leave it as an unbacked SHALL.
