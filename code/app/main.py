import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.data import LOCATIONS, PINCODE_SOURCE, SCHEMES, filter_schemes, find_scheme
from app.models import (
    ErrorDetail,
    ErrorEnvelope,
    LocationRecord,
    ResponseMeta,
    Scheme,
    SuccessEnvelope,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DEMO_API_KEY = "bharatos_demo_2026"


class ApiProblem(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


app = FastAPI(
    title="BharatOS Prototype API",
    description="Phase-one prototype for unified Indian public scheme and civic-data access.",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount(
    "/diagrams",
    StaticFiles(directory=PROJECT_DIR / "docs" / "diagrams" / "rendered"),
    name="diagrams",
)
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.exception_handler(ApiProblem)
async def api_problem_handler(_: Request, exc: ApiProblem) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorDetail(code=exc.code, message=exc.message, request_id=uuid4().hex[:12])
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


def require_demo_key(x_api_key: str | None = Header(default=None)) -> str:
    if x_api_key != DEMO_API_KEY:
        raise ApiProblem(
            status_code=401,
            code="INVALID_API_KEY",
            message="Provide the phase-one demo key in the X-API-Key header.",
        )
    return x_api_key


def response_meta(source_name: str, result_count: int | None = None) -> ResponseMeta:
    return ResponseMeta(
        source=source_name,
        last_verified=max(item.source.last_verified for item in SCHEMES),
        generated_at=datetime.now(UTC),
        result_count=result_count,
    )


def common_context(active_page: str) -> dict[str, str]:
    return {"active_page": active_page, "demo_key": DEMO_API_KEY}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(
    request: Request,
    q: str = "",
    category: str = "",
    state: str = "",
    audience: str = "",
) -> HTMLResponse:
    schemes = filter_schemes(q=q, category=category, state=state, audience=audience)
    context = {
        **common_context("explore"),
        "schemes": schemes,
        "all_schemes": SCHEMES,
        "filters": {"q": q, "category": category, "state": state, "audience": audience},
        "categories": sorted({item.category for item in SCHEMES}),
        "states": sorted({state_name for item in SCHEMES for state_name in item.states}),
        "audiences": sorted({aud for item in SCHEMES for aud in item.audiences}),
    }
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@app.get("/schemes/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def scheme_detail(request: Request, slug: str) -> HTMLResponse:
    scheme = find_scheme(slug)
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
        context={**common_context("explore"), "scheme": scheme},
    )


@app.get("/developers", response_class=HTMLResponse, include_in_schema=False)
async def developer_console(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="developers.html",
        context={**common_context("developers"), "scheme_count": len(SCHEMES)},
    )


@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def api_docs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="docs.html",
        context={**common_context("docs")},
    )


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_overview(request: Request) -> HTMLResponse:
    source_rows = [
        {
            "name": "myScheme snapshots",
            "records": len(SCHEMES),
            "status": "Healthy",
            "age": "Today",
        },
        {
            "name": "India Post PIN directory",
            "records": len(LOCATIONS),
            "status": "Healthy",
            "age": "Today",
        },
        {"name": "API Setu adapter", "records": 0, "status": "Planned", "age": "Phase 2"},
    ]
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={**common_context("admin"), "source_rows": source_rows},
    )


@app.get(
    "/api/v1/schemes",
    response_model=SuccessEnvelope[list[Scheme]],
    dependencies=[Depends(require_demo_key)],
    tags=["Schemes"],
)
async def api_list_schemes(
    q: str = "", category: str = "", state: str = "", audience: str = ""
) -> SuccessEnvelope[list[Scheme]]:
    results = filter_schemes(q=q, category=category, state=state, audience=audience)
    return SuccessEnvelope(
        data=results,
        meta=response_meta("Curated official-source snapshots", result_count=len(results)),
    )


@app.get(
    "/api/v1/schemes/{scheme_id}",
    response_model=SuccessEnvelope[Scheme],
    dependencies=[Depends(require_demo_key)],
    tags=["Schemes"],
)
async def api_get_scheme(scheme_id: str) -> SuccessEnvelope[Scheme]:
    scheme = find_scheme(scheme_id)
    if scheme is None:
        raise ApiProblem(404, "SCHEME_NOT_FOUND", f"No prototype scheme matches '{scheme_id}'.")
    return SuccessEnvelope(
        data=scheme,
        meta=response_meta(scheme.source.name, result_count=1),
    )


@app.get(
    "/api/v1/locations/pincode/{pincode}",
    response_model=SuccessEnvelope[LocationRecord],
    dependencies=[Depends(require_demo_key)],
    tags=["Locations"],
)
async def api_get_pincode(pincode: str) -> SuccessEnvelope[LocationRecord]:
    if not re.fullmatch(r"\d{6}", pincode):
        raise ApiProblem(422, "INVALID_PINCODE", "A PIN code must contain exactly six digits.")
    location = LOCATIONS.get(pincode)
    if location is None:
        raise ApiProblem(
            404,
            "PINCODE_NOT_FOUND",
            "This phase-one prototype contains only 147004, 110001 and 560001.",
        )
    return SuccessEnvelope(
        data=location,
        meta=ResponseMeta(
            source=PINCODE_SOURCE.name,
            last_verified=PINCODE_SOURCE.last_verified,
            generated_at=datetime.now(UTC),
            result_count=1,
        ),
    )
