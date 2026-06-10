"""Model-provider runtime: declarative spec → LiveKit component resolution.

See openspec/changes/multi-model-runtime for the design. Split into two modules:

  constants.py  — import-light shape helpers + enums. NO livekit/plugin imports,
                  so the FastAPI process can validate `models` blocks without the
                  agent's heavy plugin graph or provider API keys.
  providers.py  — actual component construction (imports inference + plugins).
"""
