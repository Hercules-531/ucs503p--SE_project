FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/bharatos-venv PATH="/opt/bharatos-venv/bin:$PATH"
WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.4
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY docs/diagrams/rendered ./docs/diagrams/rendered
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/ingest_snapshots.py ./scripts/ingest_snapshots.py
COPY scripts/ingest_ogd_pincode.py ./scripts/ingest_ogd_pincode.py
COPY scripts/ingest_pincode_mirror.py ./scripts/ingest_pincode_mirror.py
COPY scripts/ingest_pib_schemes.py ./scripts/ingest_pib_schemes.py
COPY scripts/ingest_pib_programmes.py ./scripts/ingest_pib_programmes.py
COPY scripts/ingest_pib_transport.py ./scripts/ingest_pib_transport.py
COPY scripts/ingest_pib_environment.py ./scripts/ingest_pib_environment.py
COPY scripts/schedule_pincode.py ./scripts/schedule_pincode.py
COPY scripts/schedule_source_checks.py ./scripts/schedule_source_checks.py
RUN useradd --create-home --uid 10001 bharatos && chown -R bharatos:bharatos /app
USER bharatos
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
