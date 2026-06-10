## 1. Provider runtime layer

- [x] 1.1 Create `agents/runtime/__init__.py` and `agents/runtime/providers.py` skeleton
- [x] 1.2 Define model spec parsing: normalize `{provider, model, via, options, language}` dicts, default `via=inference`
- [x] 1.3 Implement lighter build dispatch (review decision: NO full registry yet): `via: inference` → `inference.LLM/STT/TTS(f"{provider}/{model}")` gateway passthrough; `via: direct` → special-case only `deepgram` (STT) and `google` (realtime), else fail loud. Defer the full `(kind,provider,via)` registry to graph-agent-builder/OQ4
- [x] 1.4 Implement `build_llm` / `build_stt` / `build_tts`: single spec → bare component, multiple → `FallbackAdapter`
- [x] 1.5 Implement `AGENT_STT_PROVIDER` global override forcing STT to direct provider regardless of spec `via`
- [x] 1.6 Implement realtime path: build `TextInputRealtimeModel` from `models.realtime` (model/voice/thinking), force latency-mitigation settings, reject non-Gemini realtime provider with explicit error
- [x] 1.7 Implement `resolve_session_components(profile, mode, env)` returning session components with built-in defaults backfilled for missing specs, AND the resolved primary model names (llm/stt/tts/realtime variant + realtime STT provider) for cost (review P1)
- [x] 1.8 Expose `KNOWN_DIRECT_PROVIDERS` as a plain string-constant set ({"deepgram","google"}) with NO plugin-factory imports, so the API process can build the validation enum without dragging LiveKit plugin imports (review P2 import-coupling)

## 2. Wire runtime into agent

- [x] 2.1 Refactor `agents/agent.py` pipeline branch to call `resolve_session_components` instead of hard-coded `FallbackAdapter` lists
- [x] 2.2 Refactor `agents/agent.py` realtime branch to build LLM/STT via resolver while preserving `TextInputRealtimeModel` and all no-op interception
- [x] 2.3 Compute effective mode in `entrypoint()` AFTER `load_profile_with_id` (`models.mode` ⊕ `AGENT_MODE` env precedence); thread the single value into both the session branch (`agent.py:308`) and `create_agent_class` (`agent.py:279`). Remove reliance on the module-global `AGENT_MODE` read at `agent.py:195`. Detect env presence with `"AGENT_MODE" in os.environ` — NOT `os.environ.get("AGENT_MODE", "realtime")`, which collapses unset→realtime and makes the "use models.mode when env unset" branch unreachable (review Finding 2 + P2)
- [x] 2.4 Verify forked child process and SIP-pinned profile both resolve `models` from re-loaded profile config (no `sys.argv` dependency)
- [x] 2.5 Record the resolved primary model names on the DB session row at start (`session_store.create_session` new field), so cost reads them instead of metrics (review P1)
- [x] 2.5a Make the recorded model-name field shape extensible (JSON list/segments, not one string per kind) — graph-runtime-executor's per-node models will put multiple LLMs in one session; the current one-name-per-kind shape forecloses that and would force a cost-channel rework. Touches 2.5 + §4 lookup, still cheap while uncommitted (2026-06-10 graph-agent-builder review, outside voice F10)

> NOTE: 2.5 must land BEFORE §4 — task 4.2 depends on the model-name channel existing. The original §1→§2→§4 order would otherwise compute cost against `llm_model == "FallbackAdapter"`.

## 3. Profile schema

- [x] 3.1 Document optional `models` block fields in `agents/profiles/example.yaml` (mode, llm/stt/tts lists, realtime, via, options)
- [x] 3.2 Add hand-written Pydantic validation for the `models` block in `agents/api/schemas.py` (config stays free-form dict elsewhere; validate this block's shape on save, return 422 on malformed/unknown provider). Source the `direct`-provider enum from the import-light `KNOWN_DIRECT_PROVIDERS` constant (task 1.8), NOT by importing factories. Validation must NOT instantiate components (no API keys / no `VAD.load()` in the API process or CI) (review Finding 3 + P2)
- [x] 3.2a Add a Gemini Live variant allowlist for `models.realtime.model`; reject known-dead variants (e.g. 3.1-live → 1007) at save time, since realtime has no FallbackAdapter net (review P3)
- [x] 3.3 Add a `models` block to one profile (e.g. `restaurant.yaml`) for pipeline end-to-end verification

## 4. Cost extension

- [x] 4.1 Extend `agents/db/cost.py` rate tables to cover new providers/models in one place
- [x] 4.2 Drive rate lookup from the model names recorded on the session row (task 2.5), NOT from metrics (`FallbackAdapter.model` returns the literal "FallbackAdapter" — verified fallback_adapter.py:80); fall back to fuzzy match only when the recorded name is unavailable (review P1)
- [x] 4.4a Freeze historical cost: `routes_sessions.py` (lines ~49-71) must read the stored cost from the session row (`raw_report_json.cost`) instead of re-running `compute_cost` at read time, so rate-table edits don't silently re-price old sessions (review P3)
- [x] 4.3 Make realtime rate selectable by the profile's Gemini Live variant, keeping the existing default as fallback
- [x] 4.5 Drive the realtime STT rate from `STT_RATES` keyed by the profile's realtime STT provider; delete the duplicated `_REALTIME_STT_RATE_PER_MIN` constant (review Finding 5)
- [x] 4.4 Ensure unknown models set `incomplete=True` instead of emitting a wrong estimate

## 5. Tests

- [x] 5.1 Unit tests for spec parsing, registry resolution, and `FallbackAdapter` assembly
- [x] 5.2 Test `AGENT_STT_PROVIDER` override and `via` selection (inference vs direct)
- [x] 5.3 Test realtime resolver: TextInputRealtimeModel built, latency settings forced, non-Gemini provider rejected
- [x] 5.4 Regression test: profiles without `models` block produce sessions identical to pre-change defaults
- [x] 5.5 Cost tests: profile-driven rate, new-provider rate, unknown-model `incomplete` flag
- [x] 5.6 Update `agents/tests/test_agent_system.py` assertions if session assembly touched
- [x] 5.7 Validation tests: valid `models` block saves (200); malformed shape and unknown provider rejected (422) (review Finding 3 / test gap)
- [x] 5.8 Mode-precedence test: `models.mode` honored when `AGENT_MODE` unset; `AGENT_MODE` env wins when set (review Finding 2 / test gap)
- [x] 5.9 Partial-backfill test: `models` declares `llm` only → declared LLM used, STT/TTS fall back to built-in defaults (spec scenario, was untested)
- [x] 5.10 Cost test: realtime STT rate resolved from `STT_RATES` by profile's realtime STT provider (review Finding 5 / test gap)

## 6. Verification

> **6.2 / 6.3 are RELEASE-BLOCKING gates, not trailing checkboxes** (2026-06-10 graph-agent-builder review, outside voice F11): they are the only live verification of the single non-negotiable CLAUDE.md constraint (TextInputRealtimeModel latency mitigation). "Behavior moved verbatim into the resolver" is exactly the kind of refactor that breaks via ordering/kwargs subtleties — offline proxies do not close them. Do not merge/deploy this change with these unchecked.

- [x] 6.1 Run `cd agents && uv run pytest tests/ -q` (baseline 147 pass + new tests)
- [ ] 6.2 Local Try-button verification: pipeline profile with `models` block + realtime default both connect and respond — REQUIRES LIVE LiveKit creds + browser; not runnable headless. Offline proxy DONE: agent.py imports clean, resolver builds both modes (test_runtime_providers), restaurant `models` block validates.
- [ ] 6.3 Confirm realtime latency unchanged (TextInputRealtimeModel intact) via session metrics — REQUIRES LIVE call. Offline proxy DONE: resolver builds TextInputRealtimeModel with forced latency settings; behavior moved verbatim from agent.py.
