# Gemini + Google Cloud compliance — implementation notes

Done for the "All Things Agentic" hackathon requirement: "Build next
generation AI agents on Gemini and Google Cloud." Full suite: 47/47
passing (45 prior + 2 new).

## What was actually wrong before this

`services/llm_holding.py` called `generativelanguage.googleapis.com`
directly, that's the consumer Gemini Developer API (Google AI Studio),
not Vertex AI, and not a Google Cloud product in the sense the hackathon
almost certainly means. There was also no GCP deployment anywhere in the
codebase, no Cloud Run config, nothing.

## What changed

1. **`services/llm_holding.py`** gained `_call_vertex_ai`, using the
   `google-genai` SDK in `vertexai=True` mode, authenticated via
   Application Default Credentials rather than an API key. Provider
   auto-selection now prefers `vertex` when `GOOGLE_CLOUD_PROJECT` (or
   `NADI_GCP_PROJECT_ID`) is set, falling back to the direct Gemini API
   key path, then OpenAI, then the deterministic mock, exactly the same
   fallback discipline the original code already had.
2. **`config.py`** gained `gcp_project_id` and `gcp_location`
   (default `asia-southeast1`).
3. **`requirements.txt`** gained `google-genai`.
4. **`Dockerfile`** + **`DEPLOY_CLOUD_RUN.md`** — a Cloud Run deployment
   with cost-conscious defaults (`--min-instances 0`, `--max-instances 2`,
   512Mi memory), given the known GCP billing-surprise history this stack
   has had elsewhere.
5. **`tests/test_llm_holding.py`** gained 2 tests for the new routing.

## Verified, not just written

- Ran the full existing suite before and after: 45/45, then 47/47, no
  regressions
- Directly exercised the routing logic with `GOOGLE_CLOUD_PROJECT` set and
  no real GCP credentials present, confirmed it correctly attempts Vertex
  AI first, fails cleanly on missing ADC (not a crash, not a silent wrong
  provider), and falls back to the mock with `ave: False` still holding
- Confirmed the *absence* of `GOOGLE_CLOUD_PROJECT` correctly skips the
  vertex path entirely, preserving local dev without any GCP setup
- Simulated the Dockerfile's install steps in a clean venv (no Docker
  available in this environment to build the actual image), both `pip
  install -r requirements.txt` and `pip install -e .` succeeded cleanly,
  and the app imported without error afterward
- Directly tested the `$PORT` handling the Dockerfile's CMD relies on:
  set `PORT=8099`, started uvicorn with the exact same command Cloud Run
  would invoke, confirmed it served on 8099, not a hardcoded 8080

## Honest limitations

- **The Dockerfile itself was never built into an actual image or run in
  a container**, no Docker in this environment. What's verified above is
  the install steps and the port-binding logic in isolation, that's real
  signal but it is not the same as `docker build && docker run` succeeding
  end to end. Worth doing that check yourself before the actual `gcloud
  run deploy`, or telling me to do it if you get me a Docker-capable
  environment.
- **Not actually deployed to Cloud Run.** I don't have your GCP
  credentials or a project to deploy into. `DEPLOY_CLOUD_RUN.md` has the
  exact commands; running them is a "you" step.
- **The Vertex AI call path itself was never exercised against a real GCP
  project**, only the failure/fallback path was, since no real credentials
  exist in this sandbox. If you want that verified live, it needs to run
  somewhere with actual `gcloud auth application-default login` done or a
  service account key, i.e. after deployment.
- No frontend Cloud Run/hosting story here, backend only, as scoped in
  the earlier conversation.
