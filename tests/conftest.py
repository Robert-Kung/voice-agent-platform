"""pytest global fixtures / env overrides.

Defence-in-depth for M6 from CODE_REVIEW.md: if any test inadvertently calls
`db.engine.get_session_factory()` without setting up its own override, it must
hit an in-memory SQLite DB, NOT the real ./data/agent_platform.db file.

We set AGENT_DB_PATH before any test module imports db.engine, so the
lazy-initialized singleton picks up the in-memory URL.
"""

import os

os.environ.setdefault("AGENT_DB_PATH", ":memory:")
