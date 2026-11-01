ARG PLAYWRIGHT_VERSION=v1.59.0-noble


# =============================================================================
# STAGE: builder — install deps into --user dir so they can be copied without root
# =============================================================================
FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS builder

WORKDIR /build

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --user -r requirements.txt


# =============================================================================
# STAGE: runtime-base — shared base: copy deps from builder, create /app, drop to pwuser
# =============================================================================
FROM mcr.microsoft.com/playwright/python:${PLAYWRIGHT_VERSION} AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/home/pwuser/.local/bin:/usr/local/bin:/usr/bin:/bin

RUN mkdir -p /app/output /app/logs \
 && chown -R pwuser:pwuser /app

COPY --from=builder --chown=pwuser:pwuser /root/.local /home/pwuser/.local

WORKDIR /app

COPY --chown=pwuser:pwuser scraper     ./scraper
COPY --chown=pwuser:pwuser config.yaml ./config.yaml

USER pwuser


# =============================================================================
# STAGE: scraper-cli — one-shot CLI scraper
# =============================================================================
FROM runtime-base AS scraper-cli

ENTRYPOINT ["python", "-m", "scraper"]
CMD []


# =============================================================================
# STAGE: mcp-server — adds mcp_server package, exposes HTTP on 8080
# =============================================================================
FROM runtime-base AS mcp-server

USER root
COPY --chown=pwuser:pwuser mcp_server ./mcp_server
USER pwuser

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "-m", "mcp_server.server"]
CMD []


# =============================================================================
# STAGE: ui-build — compiles the Vue app into ui/dist
# =============================================================================
FROM oven/bun:1.4.4-slim AS bun-binary

FROM node:24-slim AS ui-build

COPY --from=bun-binary /usr/local/bin/bun /usr/local/bin/bun
WORKDIR /ui
COPY ui/package.json ui/bun.lock ./
RUN bun install --frozen-lockfile
COPY ui/ ./
RUN bun run build


# =============================================================================
# STAGE: ui-server — FastAPI service that also serves the Vue build, port 8090
# =============================================================================
FROM python:3.13-slim AS ui-server

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UI_HOST=0.0.0.0

RUN useradd --uid 1001 --create-home uiuser \
 && mkdir -p /app/output /app/logs /app/config-backups \
 && chown -R uiuser:uiuser /app

WORKDIR /app

COPY ui_server/requirements.txt ./ui-requirements.txt
RUN pip install --no-cache-dir -r ui-requirements.txt

COPY --chown=uiuser:uiuser scraper/__init__.py scraper/config_loader.py scraper/types.py ./scraper/
COPY --chown=uiuser:uiuser ui_server ./ui_server
COPY --chown=uiuser:uiuser --from=ui-build /ui/dist ./ui/dist

USER uiuser

EXPOSE 8090

ENTRYPOINT ["python", "-m", "ui_server"]
CMD []


# =============================================================================
# STAGE: bot — node + claude-code + supercronic; runs scheduled scrapes via claude
# =============================================================================
FROM node:20-slim AS bot

ARG SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/latest/download/supercronic-linux-amd64
ARG YQ_URL=https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "$SUPERCRONIC_URL" -o /usr/local/bin/supercronic \
 && chmod +x /usr/local/bin/supercronic \
 && curl -fsSL "$YQ_URL" -o /usr/local/bin/yq \
 && chmod +x /usr/local/bin/yq

RUN npm install -g @anthropic-ai/claude-code

WORKDIR /workspace/scraper-bot

COPY --chown=node:node config.yaml            /workspace/config.yaml
COPY --chown=node:node cron                   ./cron
COPY --chown=node:node prompts                ./prompts
COPY --chown=node:node claude/mcp.json.example ./.mcp.json

RUN SCHEDULE="$(yq -r '.bot.schedule' /workspace/config.yaml)" \
 && echo "Generated cron schedule: $SCHEDULE" \
 && printf '%s /bin/sh /workspace/scraper-bot/cron/run-scraper.sh\n' "$SCHEDULE" \
    > cron/scraper-crontab \
 && chmod +x cron/entrypoint.sh cron/run-scraper.sh \
 && mkdir -p /home/node/.claude \
 && touch /home/node/.claude.json \
 && chown -R node:node /home/node /workspace

USER node

ENTRYPOINT ["/usr/local/bin/supercronic"]
CMD ["/workspace/scraper-bot/cron/scraper-crontab"]
