# 멀티-스테이지 빌드: 파이썬 런타임 + 동봉된 프론트 정적 파일.
# 평가 환경과 동일하게 Python만으로 실행되도록 설계.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 시스템 의존성 (pandas·pyarrow 빌드는 wheel로 해결되므로 최소)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY packages ./packages
COPY apps ./apps
COPY data/processed ./data/processed

RUN pip install -U pip && pip install -e .

# 기본 설정 (compose/k8s에서 오버라이드)
ENV LLM_PROVIDER=none \
    DATA_DIR=/app/data/processed \
    SESSION_DB=/app/data/sessions.sqlite3 \
    LOG_JSON=true \
    RATE_LIMIT_PER_MIN=60 \
    AGENT_MAX_TOOL_CALLS=8

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/livez || exit 1

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
