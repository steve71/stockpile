# Use a slim Python 3.12 image compatible with ARM64 (Raspberry Pi)
FROM python:3.12-slim-bookworm

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy the workspace root files (pyproject.toml, uv.lock) and all member project sources.
# This ensures `uv` has access to all pyproject.toml files for dependency resolution.
COPY pyproject.toml uv.lock ./
COPY shared/ ./shared/
COPY options-scanner/ ./options-scanner/

# Install dependencies first (better caching)
# `--frozen` ensures we use the exact versions from uv.lock.
# `--no-dev` skips dev dependencies.
# `--no-install-project` prevents uv from trying to install the local workspace projects themselves
# at this stage, focusing only on their external dependencies. This layer is highly cacheable.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Streamlit runs on 8501 by default
EXPOSE 8501

# Run the app
# --server.address=0.0.0.0 is required for Docker to allow external access
ENTRYPOINT ["uv", "run", "--no-sync", "streamlit", "run", "options-scanner/run_app.py", "--server.address=0.0.0.0", "--server.port=8501"]