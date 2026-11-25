"""
Production AI Agent — Part 6 Final Project.

Đáp ứng 12 tiêu chí Production Readiness:
  - /health (liveness) & /ready (readiness kiểm tra Redis)
  - X-API-Key authentication (401)
  - Rate limiting sliding window trong Redis (429 + Retry-After)
  - Cost guard trong Redis (402)
  - 12-Factor config từ biến môi trường
  - Structured JSON logging
  - Graceful shutdown qua FastAPI lifespan
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mỗi dòng log của app thành 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    log = logging.getLogger("production_agent")
    log.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        log.addHandler(handler)
    log.propagate = False
    return log


logger = _setup_logger()
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "agent_startup",
        extra={
            "extra_fields": {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        },
    )
    yield
    logger.info(
        "agent_shutdown",
        extra={"extra_fields": {"event": "shutdown", "status": "graceful"}},
    )
    close_redis()


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_error",
        extra={
            "extra_fields": {
                "event": "error",
                "path": request.url.path,
                "error_type": type(exc).__name__,
            }
        },
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = None


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn sống, kể cả khi Redis mất kết nối."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 2),
    }


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi Redis sẵn sàng, 503 khi Redis không kết nối được."""
    if not redis_healthy():
        logger.warning(
            "readiness_failed",
            extra={"extra_fields": {"event": "ready_check", "redis": "disconnected"}},
        )
        raise HTTPException(status_code=503, detail="Redis is not available")
    return {"status": "ready", "redis": "connected"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    started = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "ask_completed",
        extra={
            "extra_fields": {
                "event": "request",
                "path": "/ask",
                "status": 200,
                "ms": elapsed_ms,
                "cost_usd": round(cost, 6),
            }
        },
    )
    return {
        "question": body.question,
        "answer": answer,
        "user_id": body.user_id,
        "cost_usd": round(cost, 6),
    }
