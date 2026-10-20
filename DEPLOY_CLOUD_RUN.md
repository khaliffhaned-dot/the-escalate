# Deploying ESCALATE™ to Cloud Run

For the hackathon's mandatory Google Cloud infrastructure requirement, and
the "must show Cloud Run running in the demo video" requirement. Internal
package name stays `nadi`, only the display name changed.

**This deploys the whole product, not just the API.** The image now includes
`frontend/`, and `api/app.py` mounts it at `/`, so the `.run.app` URL opens
the operator console directly. Earlier revisions of this guide said backend
only; that is no longer true.

## Before anything else: the free credit

The hackathon rules included $150 in free GCP credit via
https://forms.gle/riGhgDSHkHeMx8Ca6, but that window **closed on August 28
at 12:00 PM PDT** and is past as of the submission deadline. Everything
below works on a normal GCP free-trial account without it.

## Step 0: Install the gcloud CLI

Not currently installed on this machine. On Windows, either download the
installer from <https://cloud.google.com/sdk/docs/install> or:

```powershell
winget install --id Google.CloudSDK -e
```

Then **open a new terminal** so `gcloud` lands on PATH.

## What you need before deploying

A GCP project with billing enabled (Cloud Run's free tier still requires a
billing account attached, it just doesn't charge you within free tier
limits).

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com aiplatform.googleapis.com cloudbuild.googleapis.com
```

## Step 1: Deploy

Run this from the repo root, where the Dockerfile is:

```bash
gcloud run deploy the-escalate \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 1Gi \
  --set-env-vars NADI_GCP_PROJECT_ID=YOUR_PROJECT_ID,NADI_GCP_LOCATION=asia-southeast1,NADI_LLM_PROVIDER=adk,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=asia-southeast1
```

> **The three `GOOGLE_*` vars are not optional, and leaving them out fails
> silently.** The `NADI_`-prefixed vars configure this app's own `Settings`
> object. They are invisible to the ADK agent, which builds its own
> `google.genai` client that resolves Vertex-vs-API-key from
> `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and
> `GOOGLE_CLOUD_LOCATION` (see `google/genai/_api_client.py`).
>
> Verified by running the agent both ways. With `NADI_*` alone it raises
> `ValueError: No API key was provided` — it went to the *Gemini Developer
> API* and never touched Vertex at all. With the `GOOGLE_*` vars set it
> reaches `aiplatform.googleapis.com` properly.
>
> This matters because the failure is invisible from outside: the agent
> errors, `llm_holding.py` catches it, and you get a perfectly good
> deterministic draft stamped `nadi-brief-2026-08-local`. The service looks
> healthy while the headline feature is not running. Step 4 below is what
> catches it.

Notes on the flags, updated from an earlier pass now that ADK is in the
dependency tree:

- **`--memory 1Gi`**, bumped from an earlier 512Mi recommendation. I
  measured the actual installed dependency footprint with ADK included:
  189MB on disk, meaningfully more than before (`google-adk` pulls in
  opentelemetry, aiohttp, cryptography). 1Gi gives real headroom rather
  than risking an out-of-memory failure the first time a judge actually
  loads it.
- **`--min-instances 0`** — scales to zero when idle, keeps this inside
  free-tier cost. Means a cold start (a few seconds) on the first request
  after idle, worth remembering if you're about to record the demo video,
  hit the URL once yourself first to warm it up before you hit record.
- **`--max-instances 2`** — hard ceiling against runaway spend.
- **`NADI_LLM_PROVIDER=adk`** — forces the ADK agent path rather than
  leaving it on `auto`, so the deployed instance is unambiguously running
  the real agent, exactly what you want for judging.

This command builds the container from source and deploys in one step,
you don't need to build/push the image separately.

## Step 2: Service account permissions for Vertex AI / Gemini

Cloud Run's default service account needs the Vertex AI User role:

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

Find your project number with:

```bash
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

## Step 3: Verify it's actually working

```bash
SERVICE_URL=$(gcloud run services describe the-escalate --region asia-southeast1 --format 'value(status.url)')
echo "$SERVICE_URL"
curl "$SERVICE_URL/health"
```

You should see the same JSON you've seen locally throughout this whole
build:

```json
{"status":"ok","version":"0.1.0","ave_enabled":false,"evaluation_codename":"berry-bison-yonder-cabin"}
```

If `ave_enabled` isn't `false` here, stop and tell me, something is
fundamentally wrong and shouldn't depend on where it's deployed.

## Step 4: Confirm the ADK agent actually runs against real credentials

This is the one thing that has never been verified live, only up to the
credentials boundary, in every test so far. This is the actual moment of
truth:

```bash
curl -X POST "$SERVICE_URL/v1/workspaces/ws_aurora/briefs" \
  -H "X-Nadi-Role: analyst" -H "Content-Type: application/json" \
  -d '{"kind":"holding"}'
```

Check the response's `model_version` field. If it starts with `adk:`,
the real agent ran successfully end to end for the first time. If it
falls back to `nadi-brief-2026-08-local`, something in the Vertex AI/ADK
path failed, and Cloud Run's logs will show why:

```bash
gcloud run services logs read the-escalate --region asia-southeast1 --limit 50
```

Paste that back to me if it falls back, I'll help diagnose it against the
actual error rather than guess.

## For the demo video

The rules require visual proof the backend is running on Google Cloud.
Options, any one satisfies it:

- Screen-record the Cloud Run dashboard in the GCP Console showing the
  service running
- Show `gcloud run services logs read` output live during the demo
- Show the `.run.app` URL in the browser address bar while using the app

## What this still doesn't include

- No Cloud SQL wiring for Cloud Run specifically, `NADI_USE_DB_STORE`
  still defaults to the in-memory store, meaning data resets whenever
  Cloud Run scales an idle instance down. Fine for judging, not for
  anything real.
- No CDN in front of the console. The static files are served by uvicorn
  from the same container, which is fine at judging scale but is not how
  you would serve them under real traffic.
