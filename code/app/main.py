import hashlib
import hmac
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Annotated
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.cache import cache_metrics, cached_records
from app.credentials import new_token, password_hash, token_hash, verify_password
from app.data import (
    INDIAN_STATES_AND_UTS,
    LOCATIONS,
    SCHEMES,
    filter_schemes,
    uncertain_filter_exclusions,
)
from app.models import (
    ErrorDetail,
    ErrorEnvelope,
    LocationRecord,
    ResponseMeta,
    Scheme,
    SuccessEnvelope,
)
from app.monitoring import monitoring_alerts, recent_api_errors, source_summaries
from app.privacy import install_access_log_filter
from app.rate_limit import RedisRateLimiter
from app.readiness import database_readiness
from app.search import (
    CatalogueFacets,
    catalogue_facets,
    indexed_scheme_page,
    indexed_schemes,
    indexed_uncertain_exclusions,
)
from app.source_checks import latest_source_checks, run_source_checks, source_check_for_url
from app.storage import (
    ApiKey,
    ApiRequestLog,
    DeveloperAccount,
    DeveloperSession,
    IngestionRun,
    SchemeIndex,
    StoredRecord,
    create_database,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
EXPECTED_DATABASE_HEADS = frozenset(
    ScriptDirectory(PROJECT_DIR / "migrations").get_heads()
)
install_access_log_filter()
DEMO_API_KEY = "bharatos_demo_2026"
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
engine = create_database(DATABASE_URL) if DATABASE_URL else None
CACHE_NAMESPACE = hashlib.sha256((DATABASE_URL or "").encode()).hexdigest()[:16]
REDIS_URL = os.getenv("REDIS_URL")
rate_limiter = (
    RedisRateLimiter(
        Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1),
        limit=int(os.getenv("API_RATE_LIMIT", "60")),
        window_seconds=int(os.getenv("API_RATE_WINDOW_SECONDS", "60")),
    )
    if REDIS_URL
    else None
)
cache_client = (
    Redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1) if REDIS_URL else None
)
login_limiter = (
    RedisRateLimiter(
        cache_client,
        limit=int(os.getenv("LOGIN_RATE_LIMIT", "10")),
        window_seconds=int(os.getenv("AUTH_RATE_WINDOW_SECONDS", "60")),
    )
    if cache_client is not None
    else None
)
registration_limiter = (
    RedisRateLimiter(
        cache_client,
        limit=int(os.getenv("REGISTRATION_RATE_LIMIT", "5")),
        window_seconds=int(os.getenv("AUTH_RATE_WINDOW_SECONDS", "60")),
    )
    if cache_client is not None
    else None
)


def current_schemes() -> list[Scheme]:
    if engine is None:
        return [Scheme.model_validate(item.model_dump(mode="json")) for item in SCHEMES]
    with Session(engine) as session:
        rows = cached_records(session, "scheme", cache_client, CACHE_NAMESPACE)
        return [Scheme.model_validate(row) for row in rows]


def current_location(pincode: str) -> LocationRecord | None:
    if engine is None:
        record = LOCATIONS.get(pincode)
        return LocationRecord.model_validate(record.model_dump(mode="json")) if record else None
    with Session(engine) as session:
        record = session.get(StoredRecord, ("location", pincode))
        return LocationRecord.model_validate(record.payload) if record else None


def current_scheme(identifier: str) -> Scheme | None:
    if engine is None:
        schemes = current_schemes()
        return next((s for s in schemes if s.id == identifier), None) or next(
            (s for s in schemes if s.slug == identifier), None
        )
    with Session(engine) as session:
        record = session.get(StoredRecord, ("scheme", identifier))
        if record is not None:
            return Scheme.model_validate(record.payload)
        return scheme_by_slug(session, identifier)


def scheme_by_slug(session: Session, slug: str) -> Scheme | None:
    payload = session.scalar(
        select(StoredRecord.payload)
        .join(SchemeIndex, SchemeIndex.identifier == StoredRecord.identifier)
        .where(StoredRecord.kind == "scheme", SchemeIndex.slug == slug)
    )
    return Scheme.model_validate(payload) if payload is not None else None


def current_scheme_by_slug(slug: str) -> Scheme | None:
    if engine is None:
        return next((scheme for scheme in current_schemes() if scheme.slug == slug), None)
    with Session(engine) as session:
        return scheme_by_slug(session, slug)


def public_source_check(url: str) -> dict | None:
    if engine is None:
        return None
    with Session(engine) as session:
        return source_check_for_url(session, url)


class ApiProblem(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, headers: dict | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


app = FastAPI(
    title="BharatOS API",
    description="Student project API for Indian public scheme and civic-data discovery.",
    version="0.1.0",
    docs_url="/reference",
    redoc_url=None,
    responses={422: {"model": ErrorEnvelope, "description": "Invalid request"}},
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount(
    "/diagrams",
    StaticFiles(directory=PROJECT_DIR / "docs" / "diagrams" / "rendered"),
    name="diagrams",
)
templates = Jinja2Templates(directory=BASE_DIR / "templates")
logger = logging.getLogger(__name__)
api_key_scheme = APIKeyHeader(name="X-API-Key", scheme_name="ApiKey", auto_error=False)
session_scheme = HTTPBearer(scheme_name="DeveloperSession", auto_error=False)
admin_scheme = APIKeyHeader(name="X-Admin-Token", scheme_name="AdminToken", auto_error=False)


def write_request_log(key_id: str, endpoint: str, status: int, duration_ms: float) -> None:
    with Session(engine) as session:
        session.add(
            ApiRequestLog(
                key_id=key_id,
                endpoint=endpoint,
                status_code=status,
                duration_ms=duration_ms,
                requested_at=datetime.now(UTC),
            )
        )
        session.commit()


@app.middleware("http")
async def protect_developer_responses(request: Request, call_next):
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        if request.url.path.startswith(("/api/v1/developers/", "/api/v1/admin/")):
            response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        key_id = getattr(request.state, "api_key_id", None)
        route = request.scope.get("route")
        if engine is not None and key_id and route is not None:
            try:
                await run_in_threadpool(
                    write_request_log,
                    key_id,
                    route.path,
                    status,
                    (perf_counter() - started) * 1000,
                )
            except Exception:
                logger.warning("Could not persist API request metadata")


@app.exception_handler(ApiProblem)
async def api_problem_handler(_: Request, exc: ApiProblem) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorDetail(code=exc.code, message=exc.message, request_id=uuid4().hex[:12])
    )
    return JSONResponse(
        status_code=exc.status_code, content=body.model_dump(mode="json"), headers=exc.headers
    )


@app.exception_handler(OperationalError)
@app.exception_handler(SQLAlchemyTimeoutError)
async def database_unavailable_handler(request: Request, exc: Exception):
    # Do not log exception text: database errors can contain SQL, credentials or user input.
    logger.warning("Database operation unavailable")
    if request.url.path.startswith("/api/v1/"):
        body = ErrorEnvelope(
            error=ErrorDetail(
                code="DATABASE_UNAVAILABLE",
                message="The data service is temporarily unavailable. Try again later.",
                request_id=uuid4().hex[:12],
            )
        )
        return JSONResponse(
            status_code=503,
            content=body.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )
    return templates.TemplateResponse(
        request=request,
        name="unavailable.html",
        context={"active_page": ""},
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith("/api/v1/"):
        return await request_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=422,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="INVALID_REQUEST",
                message="The request contains invalid or missing fields.",
                request_id=uuid4().hex[:12],
            )
        ).model_dump(mode="json"),
    )


@app.get("/health/live", tags=["Health"])
def liveness() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def readiness() -> JSONResponse:
    checks = {"database": "not_configured", "redis": "not_configured"}
    if engine is not None:
        checks["database"] = database_readiness(engine, EXPECTED_DATABASE_HEADS)
    if cache_client is not None:
        try:
            cache_client.ping()
            checks["redis"] = "ok"
        except RedisError:
            checks["redis"] = "unavailable"
    ready = all(value in {"ok", "not_configured"} for value in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "unavailable", "checks": checks},
        headers={"Cache-Control": "no-store"},
    )


def require_demo_key(request: Request, x_api_key: str | None = Depends(api_key_scheme)) -> str:
    if engine is None and x_api_key == DEMO_API_KEY:
        return x_api_key
    if engine is not None and x_api_key:
        with Session(engine) as session:
            key = session.scalar(select(ApiKey).where(ApiKey.key_hash == token_hash(x_api_key)))
            if key is not None and key.revoked_at is None:
                request.state.api_key_id = key.id
                if rate_limiter is not None:
                    try:
                        decision = rate_limiter.check(key.id)
                    except RedisError:
                        raise ApiProblem(
                            503,
                            "RATE_LIMIT_UNAVAILABLE",
                            "API rate limiting is temporarily unavailable.",
                        ) from None
                    if not decision.allowed:
                        raise ApiProblem(
                            429,
                            "RATE_LIMITED",
                            "API request limit exceeded.",
                            headers={"Retry-After": str(decision.retry_after)},
                        )
                return x_api_key
    raise ApiProblem(
        status_code=401,
        code="INVALID_API_KEY",
        message="Provide a valid API key in the X-API-Key header.",
    )


class DeveloperCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


def enforce_auth_limit(request: Request) -> None:
    if engine is None:
        return
    is_login = request.url.path.endswith("/login")
    limiter = login_limiter if is_login else registration_limiter
    if limiter is None:
        return
    client_host = request.client.host if request.client else "unknown"
    identifier = hashlib.sha256(client_host.encode()).hexdigest()
    operation = "login" if is_login else "registration"
    try:
        decision = limiter.check(f"auth:{operation}:{identifier}")
    except RedisError:
        raise ApiProblem(
            503, "RATE_LIMIT_UNAVAILABLE", "Rate limiting is temporarily unavailable."
        ) from None
    if not decision.allowed:
        raise ApiProblem(
            429,
            "RATE_LIMITED",
            "Too many attempts. Try again later.",
            headers={"Retry-After": str(decision.retry_after)},
        )


def account_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(session_scheme)],
) -> int:
    if engine is None or credentials is None:
        raise ApiProblem(401, "INVALID_SESSION", "A valid developer session is required.")
    token = credentials.credentials
    with Session(engine) as session:
        record = session.get(DeveloperSession, token_hash(token))
        if record is None:
            raise ApiProblem(401, "INVALID_SESSION", "A valid developer session is required.")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            # SQLite drops timezone information; stored naive values represent UTC.
            expires_at = expires_at.replace(tzinfo=UTC)
        else:
            expires_at = expires_at.astimezone(UTC)
        if expires_at <= datetime.now(UTC):
            raise ApiProblem(401, "INVALID_SESSION", "A valid developer session is required.")
        return record.account_id


@app.post(
    "/api/v1/developers/register",
    status_code=201,
    tags=["Developer access"],
    dependencies=[Depends(enforce_auth_limit)],
)
def register_developer(credentials: DeveloperCredentials) -> dict:
    if engine is None:
        raise ApiProblem(503, "DATABASE_REQUIRED", "Configure a database for developer access.")
    email = credentials.email.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ApiProblem(422, "INVALID_EMAIL", "Enter a valid email address.")
    with Session(engine) as session:
        session.add(
            DeveloperAccount(email=email, password_hash=password_hash(credentials.password))
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise ApiProblem(409, "ACCOUNT_EXISTS", "An account with this email exists.") from None
    return {"message": "Account created. Sign in to create an API key."}


@app.post(
    "/api/v1/developers/login",
    tags=["Developer access"],
    dependencies=[Depends(enforce_auth_limit)],
)
def login_developer(credentials: DeveloperCredentials) -> dict:
    if engine is None:
        raise ApiProblem(503, "DATABASE_REQUIRED", "Configure a database for developer access.")
    with Session(engine) as session:
        account = session.scalar(
            select(DeveloperAccount).where(
                DeveloperAccount.email == credentials.email.strip().casefold()
            )
        )
        if account is None or not verify_password(credentials.password, account.password_hash):
            raise ApiProblem(401, "INVALID_CREDENTIALS", "Invalid email or password.")
        token = new_token("bst_")
        expiry = datetime.now(UTC) + timedelta(hours=8)
        session.add(
            DeveloperSession(token_hash=token_hash(token), account_id=account.id, expires_at=expiry)
        )
        session.commit()
    return {"session_token": token, "expires_at": expiry.isoformat()}


@app.post("/api/v1/developers/logout", tags=["Developer access"])
def logout_developer(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(session_scheme)],
    account_id: int = Depends(account_session),
) -> dict:
    with Session(engine) as session:
        record = session.get(DeveloperSession, token_hash(credentials.credentials))
        if record is not None and record.account_id == account_id:
            session.delete(record)
            session.commit()
    return {"message": "Signed out."}


@app.post("/api/v1/developers/keys", status_code=201, tags=["Developer access"])
def create_developer_key(account_id: int = Depends(account_session)) -> dict:
    raw_key = new_token("bsk_")
    key_id = uuid4().hex
    with Session(engine) as session:
        session.add(
            ApiKey(
                id=key_id,
                account_id=account_id,
                key_hash=token_hash(raw_key),
                prefix=raw_key[:12],
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    return {"id": key_id, "key": raw_key, "message": "Save this key; it will not be shown again."}


@app.get("/api/v1/developers/keys", tags=["Developer access"])
def list_developer_keys(account_id: int = Depends(account_session)) -> dict:
    with Session(engine) as session:
        keys = session.scalars(select(ApiKey).where(ApiKey.account_id == account_id)).all()
        return {
            "keys": [
                {"id": key.id, "prefix": key.prefix, "revoked": key.revoked_at is not None}
                for key in keys
            ]
        }


@app.get("/api/v1/developers/usage", tags=["Developer access"])
def developer_usage(account_id: int = Depends(account_session)) -> dict:
    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        row = session.execute(
            select(
                func.count(ApiRequestLog.id),
                func.avg(ApiRequestLog.duration_ms),
                func.count().filter(ApiRequestLog.requested_at.between(day_start, now)),
                func.count().filter(ApiRequestLog.status_code.between(200, 299)),
            )
            .join(ApiKey, ApiRequestLog.key_id == ApiKey.id)
            .where(ApiKey.account_id == account_id)
        ).one()
        counts = session.execute(
            select(ApiRequestLog.endpoint, func.count(ApiRequestLog.id))
            .join(ApiKey, ApiRequestLog.key_id == ApiKey.id)
            .where(ApiKey.account_id == account_id)
            .group_by(ApiRequestLog.endpoint)
            .order_by(ApiRequestLog.endpoint)
        ).all()
    return {
        "total_requests": row[0],
        "average_duration_ms": round(row[1], 2) if row[1] is not None else None,
        "requests_today": row[2],
        "success_rate": round(row[3] / row[0], 4) if row[0] else None,
        "endpoints": [{"path": endpoint, "count": count} for endpoint, count in counts],
    }


def require_admin(token: Annotated[str | None, Depends(admin_scheme)]) -> None:
    if engine is None or len(ADMIN_TOKEN) < 32:
        raise ApiProblem(503, "ADMIN_UNAVAILABLE", "Administrator monitoring is not configured.")
    if token is None or not hmac.compare_digest(token.encode(), ADMIN_TOKEN.encode()):
        raise ApiProblem(401, "INVALID_ADMIN_TOKEN", "A valid administrator token is required.")


@app.get("/api/v1/admin/overview", tags=["Administration"], dependencies=[Depends(require_admin)])
def admin_data() -> dict:
    with Session(engine) as session:
        counts = session.execute(
            select(StoredRecord.kind, func.count()).group_by(StoredRecord.kind)
        ).all()
        total = session.scalar(select(func.count()).select_from(ApiRequestLog)) or 0
        failures = (
            session.scalar(
                select(func.count())
                .select_from(ApiRequestLog)
                .where(ApiRequestLog.status_code >= 400)
            )
            or 0
        )
        api_errors = recent_api_errors(session)
        runs = session.scalars(
            select(IngestionRun).order_by(IngestionRun.id.desc()).limit(10)
        ).all()
        # Only structured diagnostics are safe to show for both legacy and current runs.
        recent_runs = [
            {
                "source": run.source,
                "status": run.status,
                "accepted": run.accepted,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "failure_code": run.failure_code,
                "failure_position": run.failure_position,
                "failure_position_kind": run.failure_position_kind,
            }
            for run in runs
        ]
        sources = source_summaries(session)
        probes = latest_source_checks(session)
    cache = cache_metrics(cache_client, CACHE_NAMESPACE)
    return {
        "record_counts": {kind: count for kind, count in counts},
        "request_count": total,
        "error_count": failures,
        "error_rate": round(failures / total, 4) if total else None,
        "recent_api_errors": api_errors,
        "recent_ingestion_runs": recent_runs,
        "sources": sources,
        "source_checks": probes,
        "cache": cache,
        "alerts": monitoring_alerts(sources, cache, probes),
    }


@app.post(
    "/api/v1/admin/source-checks", tags=["Administration"], dependencies=[Depends(require_admin)]
)
def check_official_sources() -> dict:
    with Session(engine) as session:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            run_source_checks(session, client)
        probes = latest_source_checks(session)
    return {"source_checks": probes}


@app.delete("/api/v1/developers/keys/{key_id}", tags=["Developer access"])
def revoke_developer_key(key_id: str, account_id: int = Depends(account_session)) -> dict:
    with Session(engine) as session:
        key = session.get(ApiKey, key_id)
        if key is None or key.account_id != account_id:
            raise ApiProblem(404, "KEY_NOT_FOUND", "API key not found.")
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            session.commit()
    return {"message": "API key revoked."}


@app.post("/api/v1/developers/keys/{key_id}/rotate", status_code=201, tags=["Developer access"])
def rotate_developer_key(key_id: str, account_id: int = Depends(account_session)) -> dict:
    raw_key = new_token("bsk_")
    replacement_id = uuid4().hex
    now = datetime.now(UTC)
    with Session(engine) as session:
        result = session.execute(
            update(ApiKey)
            .where(
                ApiKey.id == key_id, ApiKey.account_id == account_id, ApiKey.revoked_at.is_(None)
            )
            .values(revoked_at=now)
        )
        if result.rowcount != 1:
            existing = session.get(ApiKey, key_id)
            if existing is None or existing.account_id != account_id:
                raise ApiProblem(404, "KEY_NOT_FOUND", "API key not found.")
            raise ApiProblem(409, "KEY_REVOKED", "A revoked key cannot be rotated.")
        session.add(
            ApiKey(
                id=replacement_id,
                account_id=account_id,
                key_hash=token_hash(raw_key),
                prefix=raw_key[:12],
                created_at=now,
            )
        )
        session.commit()
    return {
        "id": replacement_id,
        "key": raw_key,
        "message": "Old key revoked. Save the replacement; it will not be shown again.",
    }


def response_meta(
    source_name: str, records: list[Scheme], result_count: int | None = None
) -> ResponseMeta:
    dates = [item.source.last_verified for item in records]
    return ResponseMeta(
        source=source_name,
        last_verified=min(dates) if dates and all(item is not None for item in dates) else None,
        generated_at=datetime.now(UTC),
        result_count=result_count,
    )


def common_context(active_page: str) -> dict[str, str]:
    return {"active_page": active_page, "demo_key": DEMO_API_KEY if engine is None else ""}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(
    request: Request,
    q: str = "",
    category: str = "",
    state: str = "",
    audience: str = "",
    include_unknown: bool = False,
    page: int = Query(default=1, ge=1, le=100000),
) -> HTMLResponse:
    page_size = 12
    filters = {"q": q, "category": category, "state": state, "audience": audience}
    if engine is not None:
        with Session(engine) as session:
            facets = catalogue_facets(session)
            uncertain_exclusions = indexed_uncertain_exclusions(session, **filters)
            schemes, total = indexed_scheme_page(
                session,
                limit=page_size,
                offset=(page - 1) * page_size,
                include_unknown=include_unknown,
                **filters,
            )
            page_count = max(1, (total + page_size - 1) // page_size)
            if page > page_count:
                page = page_count
                schemes, total = indexed_scheme_page(
                    session,
                    limit=page_size,
                    offset=(page - 1) * page_size,
                    include_unknown=include_unknown,
                    **filters,
                )
    else:
        all_schemes = current_schemes()
        facets = CatalogueFacets(
            len(all_schemes),
            sorted({item.category for item in all_schemes}),
            sorted({name for item in all_schemes for name in item.states}),
            sorted({name for item in all_schemes for name in item.audiences}),
        )
        uncertain_exclusions = uncertain_filter_exclusions(all_schemes, **filters)
        matched = sorted(
            filter_schemes(
                records=all_schemes,
                include_unknown=include_unknown,
                **filters,
            ),
            key=lambda item: item.id,
        )
        total = len(matched)
        page_count = max(1, (total + page_size - 1) // page_size)
        page = min(page, page_count)
        schemes = matched[(page - 1) * page_size : page * page_size]

    def page_link(number: int) -> str:
        params = {key: value for key, value in filters.items() if value}
        if include_unknown:
            params["include_unknown"] = "true"
        params["page"] = str(number)
        return "/?" + urlencode(params)

    context = {
        **common_context("explore"),
        "schemes": schemes,
        "catalogue_count": facets.record_count,
        "total_matches": total,
        "page": page,
        "page_count": page_count,
        "previous_page_url": page_link(page - 1) if page > 1 else None,
        "next_page_url": page_link(page + 1) if page < page_count else None,
        "filters": {**filters, "include_unknown": include_unknown},
        "categories": facets.categories,
        "states": sorted(INDIAN_STATES_AND_UTS.union(facets.states)),
        "audiences": facets.audiences,
        "uncertain_exclusions": uncertain_exclusions,
    }
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@app.get("/schemes/{slug}", response_class=HTMLResponse, include_in_schema=False)
def scheme_detail(request: Request, slug: str) -> HTMLResponse:
    scheme = current_scheme_by_slug(slug)
    if scheme is None:
        return templates.TemplateResponse(
            request=request,
            name="not_found.html",
            context={**common_context("explore"), "item_type": "scheme"},
            status_code=404,
        )
    return templates.TemplateResponse(
        request=request,
        name="scheme_detail.html",
        context={
            **common_context("explore"),
            "scheme": scheme,
            "source_check": public_source_check(str(scheme.source.url)),
        },
    )


@app.get("/locations", response_class=HTMLResponse, include_in_schema=False)
def public_location_search(request: Request, pincode: str = "") -> HTMLResponse:
    query = pincode.strip()
    location = None
    error = None
    if query:
        if not re.fullmatch(r"[0-9]{6}", query):
            error = "Enter a six-digit PIN code using digits 0–9."
        else:
            location = current_location(query)
            if location is None:
                error = "No record for this PIN code is available in the loaded data."
    response = templates.TemplateResponse(
        request=request,
        name="locations.html",
        context={
            **common_context("locations"),
            "pincode": query[:32],
            "location": location,
            "error": error,
            "source_check": public_source_check(str(location.source.url)) if location else None,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/developers", response_class=HTMLResponse, include_in_schema=False)
def developer_console(request: Request) -> HTMLResponse:
    schemes = current_schemes()
    return templates.TemplateResponse(
        request=request,
        name="developers.html",
        context={
            **common_context("developers"),
            "scheme_count": len(schemes),
            "category_count": len({scheme.category for scheme in schemes}),
        },
    )


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def api_docs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="docs.html",
        context={**common_context("docs")},
    )


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_overview(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            **common_context("admin"),
            "admin_configured": engine is not None and len(ADMIN_TOKEN) >= 32,
        },
    )


@app.get(
    "/api/v1/schemes",
    response_model=SuccessEnvelope[list[Scheme]],
    dependencies=[Depends(require_demo_key)],
    tags=["Schemes"],
    responses={
        401: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
def api_list_schemes(
    q: str = "",
    category: str = "",
    state: str = "",
    audience: str = "",
    include_unknown: bool = False,
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1000000),
) -> SuccessEnvelope[list[Scheme]]:
    if offset and limit is None:
        raise ApiProblem(422, "INVALID_REQUEST", "The offset parameter requires a limit.")
    if limit is not None:
        if engine is not None:
            with Session(engine) as session:
                results, total = indexed_scheme_page(
                    session,
                    limit=limit,
                    offset=offset,
                    q=q,
                    category=category,
                    state=state,
                    audience=audience,
                    include_unknown=include_unknown,
                )
                uncertain = indexed_uncertain_exclusions(
                    session, q=q, category=category, state=state, audience=audience
                )
        else:
            catalogue = current_schemes()
            matched = sorted(
                filter_schemes(
                    q=q,
                    category=category,
                    state=state,
                    audience=audience,
                    records=catalogue,
                    include_unknown=include_unknown,
                ),
                key=lambda item: item.id,
            )
            total, results = len(matched), matched[offset : offset + limit]
            uncertain = uncertain_filter_exclusions(
                catalogue, q=q, category=category, state=state, audience=audience
            )
        metadata_records = results or (catalogue if engine is None else current_schemes())
        metadata = response_meta(
            "Curated official-source snapshots", metadata_records, len(results)
        )
        metadata.total_count, metadata.limit, metadata.offset = total, limit, offset
        metadata.uncertain_excluded_count = 0 if include_unknown else uncertain
        metadata.uncertain_included_count = uncertain if include_unknown else 0
        return SuccessEnvelope(data=results, meta=metadata)
    if engine is not None and any(value.strip() for value in (q, category, state, audience)):
        with Session(engine) as session:
            results = indexed_schemes(
                session,
                q=q,
                category=category,
                state=state,
                audience=audience,
                include_unknown=include_unknown,
            )
            uncertain = indexed_uncertain_exclusions(
                session, q=q, category=category, state=state, audience=audience
            )
        metadata_records = results if results else current_schemes()
    else:
        catalogue = current_schemes()
        results = filter_schemes(
            q=q,
            category=category,
            state=state,
            audience=audience,
            records=catalogue,
            include_unknown=include_unknown,
        )
        metadata_records = results or catalogue
        uncertain = uncertain_filter_exclusions(
            catalogue, q=q, category=category, state=state, audience=audience
        )
    metadata = response_meta(
        "Curated official-source snapshots", metadata_records, result_count=len(results)
    )
    metadata.uncertain_excluded_count = 0 if include_unknown else uncertain
    metadata.uncertain_included_count = uncertain if include_unknown else 0
    return SuccessEnvelope(data=results, meta=metadata)


@app.get(
    "/api/v1/schemes/{scheme_id}",
    response_model=SuccessEnvelope[Scheme],
    dependencies=[Depends(require_demo_key)],
    tags=["Schemes"],
    responses={
        401: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
def api_get_scheme(scheme_id: str) -> SuccessEnvelope[Scheme]:
    scheme = current_scheme(scheme_id)
    if scheme is None:
        raise ApiProblem(404, "SCHEME_NOT_FOUND", f"No prototype scheme matches '{scheme_id}'.")
    return SuccessEnvelope(
        data=scheme,
        meta=ResponseMeta(
            source=scheme.source.name,
            last_verified=scheme.source.last_verified,
            generated_at=datetime.now(UTC),
            result_count=1,
        ),
    )


@app.get(
    "/api/v1/locations/pincode/{pincode}",
    response_model=SuccessEnvelope[LocationRecord],
    dependencies=[Depends(require_demo_key)],
    tags=["Locations"],
    responses={
        401: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        429: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
def api_get_pincode(pincode: str) -> SuccessEnvelope[LocationRecord]:
    if not re.fullmatch(r"[0-9]{6}", pincode):
        raise ApiProblem(422, "INVALID_PINCODE", "A PIN code must contain exactly six digits.")
    location = current_location(pincode)
    if location is None:
        raise ApiProblem(
            404,
            "PINCODE_NOT_FOUND",
            "No location was found for this PIN code in the available records.",
        )
    return SuccessEnvelope(
        data=location,
        meta=ResponseMeta(
            source=location.source.name,
            last_verified=location.source.last_verified,
            generated_at=datetime.now(UTC),
            result_count=1,
        ),
    )
