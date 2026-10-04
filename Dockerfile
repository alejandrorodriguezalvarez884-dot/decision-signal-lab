# Production image: the static site served by the FastAPI app, so the site and the on-demand
# analysis share one origin.

FROM node:24-alpine AS web
WORKDIR /repo/site
COPY site/package.json site/package-lock.json ./
RUN npm ci
# The site reads the published dataset from ../radar at build time.
COPY radar/ /repo/radar/
COPY site/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
# The dataset: releases the study already read are served from it, at no cost.
COPY radar/ ./radar/
COPY --from=web /repo/site/dist ./static
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src \
    RADAR_STATIC_DIR=/app/static DECISIONSIGNAL_HTTP_CACHE=off
EXPOSE 8080
CMD ["uvicorn", "decisionsignal.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
