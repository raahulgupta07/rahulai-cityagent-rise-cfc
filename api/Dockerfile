# CFC Forecaster — API image (self-contained: FastAPI + engine)
#
# Build context = repo ROOT (see docker-compose.prod.yml) so the engine (src/*.py),
# which the runner subprocesses for real pipeline stages, is baked in alongside the API.
# data/ + models/ + reports/ are NOT baked (327MB parquet) — mounted as volumes at runtime.
# pinned to bookworm (Debian 12): trixie's apt (sqv) rejects Microsoft's SHA1-signed
# ODBC repo key; bookworm's gpgv accepts it. Matches the debian/12 MS package repo below.
FROM python:3.11-slim-bookworm

# ODBC + Microsoft SQL Server driver 18 (Fabric SQL endpoint reads, deps/fabric.py)
# + libgomp1 (OpenMP runtime required by LightGBM)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg unixodbc unixodbc-dev libgomp1 \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/api

# API deps + engine (ML) deps in one layer
COPY api/requirements.txt api/requirements-engine.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-engine.txt

# API code + engine code (both needed at runtime)
COPY api/ /app/api/
COPY src/ /app/src/
COPY fabric_user_connector.py /app/fabric_user_connector.py

ENV PYTHONPATH=/app/api
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
