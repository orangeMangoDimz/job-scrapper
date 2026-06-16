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

RUN mkdir -p /app \
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

RUN chmod +x cron/entrypoint.sh cron/run-scraper.sh \
 && mkdir -p /home/node/.claude \
 && touch /home/node/.claude.json \
 && chown -R node:node /home/node /workspace

USER node

ENTRYPOINT ["/workspace/scraper-bot/cron/entrypoint.sh"]
CMD []
