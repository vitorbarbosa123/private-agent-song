# syntax=docker/dockerfile:1
# Imagem da assistente da Empório da Música.
#   runtime: interface web (Streamlit) e comandos de linha (chat, avaliação, painel da equipe)
#   dev:     runtime + dependências de teste (pytest)

FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# Dependências primeiro: a camada só é refeita quando pyproject/uv.lock mudam.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY data ./data
COPY evals ./evals
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Os dados tratados são gerados no build: o pipeline é determinístico e não precisa de chave.
RUN emporio-clean-data

# Usuário sem privilégios; var/ guarda conversas e atendimentos (montado como volume).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/var /app/evals/results \
    && chown -R app:app /app/var /app/data/processed /app/evals/results
ENV EMPORIO_STATE_DIR=/app/var


FROM base AS runtime
USER app
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "src/emporio/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]


FROM base AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
COPY tests ./tests
USER app
# O usuário sem privilégios não escreve em /app: desliga o cache do pytest.
ENV PYTEST_ADDOPTS="-p no:cacheprovider"
CMD ["pytest", "-q"]
