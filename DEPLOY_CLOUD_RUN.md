# Deploying The Escalate's backend to Cloud Run

For the hackathon's mandatory Google Cloud infrastructure requirement, and
the "must show Cloud Run running in the demo video" requirement. Internal
package name stays `nadi`, only the display name changed.

## Before anything else: the free credit

The hackathon rules include $150 in free GCP credit, request it at
https://forms.gle/riGhgDSHkHeMx8Ca6, **deadline August 28 12:00 PM PDT
(August 29, 3:00 AM MYT), or while supplies last.** Reviewed within 72
hours, not guaranteed. If that window has already passed for you, skip to
the next section, everything below still works on a normal free-trial GCP
account, just without the extra cushion.

## What you need before deploying

A GCP project with billing enabled (Cloud Run's free tier still requires a
billing account attached, it just doesn't charge you within free tier
limits).

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com aiplatform.googleapis.com
```

## Step 1: Deploy

Run this from the repo root, where the Dockerfile is:

```bash
gcloud run deploy the-escalate-backend \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 1Gi \
  --set-env-vars NADI_GCP_PROJECT_ID=YOUR_PROJECT_ID,NADI_GCP_LOCATION=asia-southeast1,NADI_LLM_PROVIDER=adk
```

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
SERVICE_URL=$(gcloud run services describe the-escalate-backend --region asia-southeast1 --format 'value(status.url)')
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
gcloud run services logs read the-escalate-backend --region asia-southeast1 --limit 50
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
- No frontend deployment here, backend only. Cloud Storage + Firebase
  Hosting would be the equivalent move for the static frontend files, not
  built yet.
