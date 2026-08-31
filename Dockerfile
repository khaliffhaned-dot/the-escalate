# Cloud Run deployment for The Escalate's backend (internal package name
# remains `nadi`, imports below are unchanged).
#
# Cloud Run listens on $PORT (injected by the platform, do not hardcode 8080
# in the app itself, uvicorn reads it here at container start). This image
# does not bake in any API keys or GCP project ID, those are set as Cloud
# Run environment variables / secrets at deploy time, see the gcloud command
# in DEPLOY_CLOUD_RUN.md.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir -e .

# NADI_USE_DB_STORE and NADI_DATABASE_URL are set at deploy time to point
# at Cloud SQL (Postgres) if you want persistence across container
# restarts, which Cloud Run does not otherwise guarantee, containers are
# ephemeral. Left unset, this falls back to the in-memory demo store,
# same limitation documented in CHANGES_REPORTING.md.
ENV NADI_APP_NAME="The Escalate"

EXPOSE 8080

CMD exec uvicorn nadi.api.app:app --host 0.0.0.0 --port ${PORT:-8080}
