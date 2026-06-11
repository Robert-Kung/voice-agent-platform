# This is an example Dockerfile that builds a minimal container for running LK Agents
# For more information on the build process, see https://docs.livekit.io/agents/ops/deployment/builds/
# syntax=docker/dockerfile:1

# Use the official UV Python base image with Python 3.13 on Debian Bookworm
# UV is a fast Python package manager that provides better performance than pip
# We use the slim variant to keep the image size smaller while still having essential tools
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# --- Build stage ---
# Install dependencies, build native extensions, and prepare the application
FROM base AS build

# Install build dependencies required for Python packages with native extensions
# gcc: C compiler needed for building Python packages with C extensions
# g++: C++ compiler needed for building Python packages with C++ extensions
# python3-dev: Python development headers needed for compilation
# We clean up the apt cache after installation to keep the image size down
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Create a new directory for our application code
# And set it as the working directory
WORKDIR /app

# Copy just the dependency files first, for more efficient layer caching
COPY pyproject.toml uv.lock ./
RUN mkdir -p src

# Install Python dependencies using UV's lock file
# --locked ensures we use exact versions from uv.lock for reproducible builds
# This creates a virtual environment and installs all dependencies
# Ensure your uv.lock file is checked in for consistency across environments
RUN uv sync --locked

# Copy only the agent entrypoints needed for model pre-download.
# This layer is cached independently from profile YAMLs and API code,
# so model downloads are skipped on redeploys that only change profiles.
# runtime/ is imported by agent.py at module level (resolve_session_components).
COPY agent.py agent_factory.py agent_tools.py ./
COPY runtime/ ./runtime/

# Pre-download any ML models or files the agent needs.
# HF_HOME must point under /app so the cache survives the multi-stage COPY.
ENV HF_HOME=/app/.hf_cache
RUN uv run "agent.py" download-files

# Copy all remaining application files into the container
COPY . .

# --- Production stage ---
# Build tools (gcc, g++, python3-dev) are not included in the final image
FROM base

# Install the `lk` CLI so the management API container can shell out to
# `lk agent status / logs / deploy / update-secrets`. Pinned to a known-good
# version; bump when Cloud requires newer features.
ARG LK_VERSION=2.16.0
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
  && curl -fsSL "https://github.com/livekit/livekit-cli/releases/download/v${LK_VERSION}/lk_${LK_VERSION}_linux_amd64.tar.gz" \
      -o /tmp/lk.tgz \
  && tar -xzf /tmp/lk.tgz -C /usr/local/bin lk \
  && rm /tmp/lk.tgz \
  && apt-get purge -y curl \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/build/building/best-practices/#user
# Use UID 1000 to match the typical host user, so bind-mounted volumes
# (e.g. ./profiles, ./data) are writable without extra chmod.
ARG UID=1000
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

WORKDIR /app

# Copy the application and virtual environment with correct ownership in a single layer
# This avoids expensive recursive chown and excludes build tools from the final image
COPY --from=build --chown=appuser:appuser /app /app

# Keep HF_HOME consistent so the runtime finds the pre-downloaded models.
ENV HF_HOME=/app/.hf_cache

# Switch to the non-privileged user for all subsequent operations
# This improves security by not running as root
USER appuser

# Run the application using UV
# UV will activate the virtual environment and run the agent.
# The "start" command tells the worker to connect to LiveKit and begin waiting for jobs.
CMD ["uv", "run", "agent.py", "start"]
