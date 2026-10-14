# The Escalate

**A governed crisis-response desk for Malaysian PR teams.** It watches the
conversation, escalates 3R-sensitive incidents into a war room, and drafts a
bilingual holding statement with a Google ADK agent that *structurally cannot
send it alone*.

Built for the **All Things Agentic Hackathon** (Google).

> *Internal package name remains `nadi`. Imports and CLI commands below use it.*

- **Barcelona Principles 4.0** evaluation — AVE/EMV is rejected at four layers,
  not merely discouraged
- **Google ADK agent** with scoped tools and a Pydantic-constrained output schema
- **Human-must-send** holding statements — no auto-publish path exists
- **3R** (Royalty · Religion · Race) risk flagging, tuned for the Malaysian market
- Tenant/RBAC permission matrix, Postgres RLS migration, weekly executive briefs

---

## Quick start (local)

**Requires Python 3.11+.** No API keys or Google Cloud account needed — the app
runs fully offline against a deterministic drafting path and seeded demo data.

```bash
git clone <your-repo-url> the-escalate && cd the-escalate
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
uvicorn nadi.api.app:app --port 8080
```

Then open **<http://127.0.0.1:8080>** — the operator console is served from the
same origin as the API.

| URL | What it is |
|-----|------------|
| <http://127.0.0.1:8080> | Operator console (Dashboard, Mentions, Evaluation, War Rooms, Holdings) |
| <http://127.0.0.1:8080/docs> | OpenAPI / Swagger UI |
| <http://127.0.0.1:8080/health> | Liveness probe |

Demo workspace id: `ws_aurora`. Switch roles with the dropdown at the bottom
of the sidebar to watch the permission matrix take effect live.

### Run the tests

```bash
pip install -e ".[dev]"
pytest -q
```

147 tests. They run offline and need no credentials, with one exception:
`test_webhook_validation_accepts_public_host` resolves a real hostname, so it fails
where DNS is blocked.

---

## Enabling the live Gemini agent

Without credentials the app uses a deterministic drafting path, so the demo
always works. Provide **either** of the following to route drafting through the
real Google ADK agent instead:

```bash
# Option A — Vertex AI on Google Cloud (what the Cloud Run deploy uses)
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=asia-southeast1

# Option B — Gemini API key
export GEMINI_API_KEY=your-key
```

> All three `GOOGLE_*` vars are required for Option A. The ADK agent builds
> its own `google.genai` client and resolves Vertex-vs-API-key from those
> variables alone — the `NADI_`-prefixed settings below are invisible to it.
> Set only `NADI_GCP_PROJECT_ID` and the agent silently calls the Gemini
> Developer API, fails on the missing key, and falls back to the
> deterministic draft. See [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md).

Restart the server. Drafts produced by the agent are stamped
`model_version: adk:gemini-3.5-flash`; the offline path is stamped
`nadi-brief-2026-08-local`, so you can always tell which one ran.

### Configuration

All settings take a `NADI_` prefix and may also come from a `.env` file.

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_GENAI_USE_VERTEXAI` | *unset* | **Required for the agent's Vertex path** — read by the genai client, not by `Settings` |
| `GOOGLE_CLOUD_PROJECT` | *unset* | GCP project for the agent's genai client (ADC auth) |
| `GOOGLE_CLOUD_LOCATION` | *unset* | Vertex region for the agent's genai client |
| `GEMINI_API_KEY` | *unset* | Direct Gemini API key |
| `NADI_GCP_PROJECT_ID` | *unset* | Project for this app's own `_call_vertex_ai` fallback |
| `NADI_GCP_LOCATION` | `asia-southeast1` | Region for that same fallback |
| `NADI_LLM_MODEL` | `gemini-3.5-flash` | Model id |
| `NADI_LLM_PROVIDER` | `auto` | `adk` · `vertex` · `gemini` · `openai` · `mock` |
| `NADI_USE_FIRESTORE` | `false` | Persist to Cloud Firestore — free on Firebase Spark, no billing account |
| `NADI_FIRESTORE_PROJECT` | *unset* | Firebase/GCP project id for Firestore |
| `GOOGLE_APPLICATION_CREDENTIALS` | *unset* | Path to the service-account JSON for Firestore |
| `NADI_USE_DB_STORE` | `false` | Use Postgres/SQLite instead of the in-memory demo store |
| `NADI_DATABASE_URL` | `sqlite:///./nadi.db` | Database connection string |
| `PORT` | `8080` | Injected by Cloud Run; do not hardcode |

`NADI_AVE_ENABLED` exists but is inert by design — see
[Product invariants](#product-invariants).

---

## Persistence — Firestore, no billing account needed

Cloud Run requires billing enabled. **Firestore does not** — it is free on the
Firebase Spark plan with no card, and a Firebase project is a Google Cloud
project. Setting three environment variables switches the whole app onto it:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccount.json
export NADI_USE_FIRESTORE=true
export NADI_FIRESTORE_PROJECT=your-project-id
```

Every document carries `org_id` and `workspace_id`, and reads are composite
filters on both, so another tenant's document is never returned rather than
filtered out afterwards. Models re-validate on read, so the product invariants
are re-applied coming *out* of the database — hand-editing a row in the
Firestore console cannot reintroduce AVE or an auto-publishing holding.

If Firestore is unreachable the service logs why and falls back to the
in-memory store rather than refusing to boot. Full walkthrough:
[`docs/FIRESTORE_SETUP.md`](docs/FIRESTORE_SETUP.md).

---

## Deploy to Cloud Run

Builds remotely with Cloud Build, so **no local Docker is required**.
Requires a billing-enabled GCP project; see the Firestore section above if you
do not have one.

```bash
PROJECT=$(gcloud config get-value project)
gcloud run deploy the-escalate --source . --region asia-southeast1 --allow-unauthenticated --min-instances 0 --max-instances 2 --memory 1Gi --set-env-vars NADI_GCP_PROJECT_ID=$PROJECT,NADI_GCP_LOCATION=asia-southeast1,NADI_LLM_PROVIDER=adk,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=asia-southeast1
```

The service account needs the **Vertex AI User** role for the agent path to
work. Cost-conscious defaults (`--min-instances 0`) mean the service scales to
zero when idle. Full walkthrough and troubleshooting: [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md).

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full diagram and the
reasoning behind each boundary.

```
frontend/            Operator console (vanilla JS), served at "/" by the API
src/nadi/
  api/               FastAPI app, routes, RBAC dependency injection
  services/
    adk_holding_agent.py   Google ADK agent — scoped tools, Pydantic output schema
    llm_holding.py         Provider selection + the shared text guards
    holding_service.py     Deterministic path, AVE regex, state machine
    listed_issuer.py       Bursa disclosure check, insider lock, clock board, halt prompt
    evaluation_service.py  AMEC IEF scoring
    reporting_service.py   Executive brief compilation + HTML
    scheduler.py           Weekly report scheduling
  connectors/        RSS, social, Telegram ingest + pipeline
  domain/            Enums, Pydantic models, RBAC matrix
  db/                SQLAlchemy models, repository, session
  data/              Aurora / Jalur Kita demo seed
schemas/migrations/  Postgres schema + row-level security
```

### Key routes

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/v1/workspaces/{ws}/mentions` | Ingested mentions with 3R flags |
| `GET` | `/v1/workspaces/{ws}/evaluation` | Live AMEC IEF evaluation |
| `POST` | `/v1/workspaces/{ws}/evaluation/lock` | Lock snapshot — rejects `include_ave` |
| `GET` | `/v1/workspaces/{ws}/war-rooms` | Crisis canvas |
| `POST` | `/v1/workspaces/{ws}/war-rooms` | Open a room; add `"listed": {"market": "main"}` for a Bursa-listed issuer |
| `GET` | `/v1/workspaces/{ws}/war-rooms/{id}/listed` | Listed-issuer view: materiality, halt prompt, insider lock, clock board |
| `POST` | `/v1/workspaces/{ws}/war-rooms/{id}/listed/materiality` | Run the Bursa disclosure check |
| `POST` | `/v1/workspaces/{ws}/war-rooms/{id}/listed/insiders` | Add an insider (starts the lock) |
| `POST` | `/v1/workspaces/{ws}/war-rooms/{id}/listed/clocks/{key}/start` | Start a regulatory clock (`/done`, `/not-applicable` to close it) |
| `POST` | `/v1/workspaces/{ws}/war-rooms/{id}/listed/halt` | Record the trading-halt decision |
| `POST` | `/v1/workspaces/{ws}/briefs` | `{"kind":"holding","mention_ids":[...]}` |
| `POST` | `/v1/workspaces/{ws}/holdings/{id}/transition` | draft → approved → sent_external |
| `GET` | `/v1/workspaces/{ws}/reports/preview?snapshot_id=...` | Executive brief HTML |
| `POST` | `/v1/workspaces/{ws}/reports/schedule` | Register a weekly brief |

Listed-issuer routes sit under `.../war-rooms/{id}/listed/...` and are described
in the next section. Auth in the demo is a header: `X-Nadi-Role: ws_admin`. Roles are `ws_admin`,
`editor`, `analyst`, `viewer`, `org_admin`, `org_auditor`.

---

## Listed-issuer war rooms (Bursa Malaysia)

A crisis at a listed company is two crises at once: the operational or reputational
event, and a capital-markets event. A war room opened with `"listed": {"market":
"main"}` (or `"ace"`), or switched on later from the **Listed issuer** button in the
console, adds four controls for the second one:

| Control | What it does |
|---------|--------------|
| **Disclosure check** | The four-question Bursa path, applied mechanically: could it affect the price or an investor's decision (unsure counts as yes), is there an exceptional circumstance *and* complete confidentiality, any leak, rumour or unusual trading. Outcome: `not_material`, `announce_now` or `withhold_and_monitor`, with next steps. |
| **Insider lock** | Who now holds unannounced information, when they were told, whether the do-not-trade notice was sent and acknowledged. Drafts the notice (playbook template T6). Releasing the lock needs a written reason and reports anyone who never acknowledged. |
| **Regulatory clock board** | Twelve clocks (Bursa, UMA reply, PDPC 72 hours, affected individuals 7 days after the PDPC, NACSA, BNM, DOSH, lenders, insurers). Immediate duties show minutes since start; timed ones count down and go overdue. The 7-day individuals clock runs from the PDPC notification, not from when you click. |
| **Trading-halt prompt** | Considers a halt when material information is unannounced and the market is open, notes after-hours, and tells you to watch when you are withholding. You record what you did (requested, approved, declined, lifted). |

The holding drafter is told where the Bursa announcement stands, and the same rules
are re-applied to whatever it writes: "do not release before the Bursa announcement",
"never call the information material or not material in public text", and a first
operational step for the Company Secretary. They do not depend on the model
remembering them.

```bash
WR=$(curl -s -X POST localhost:8080/v1/workspaces/ws_aurora/war-rooms \
  -H 'Content-Type: application/json' -H 'X-Nadi-Role: ws_admin' \
  -d '{"title":"Ransomware at KL hub","severity":"critical","listed":{"market":"main"}}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -X POST localhost:8080/v1/workspaces/ws_aurora/war-rooms/$WR/listed/materiality \
  -H 'Content-Type: application/json' -H 'X-Nadi-Role: ws_admin' \
  -d '{"could_affect_price":"yes","exceptional_and_confidential":false}'
```

**It records and prompts; it never files.** Nothing here submits to Bursa, the PDPC,
NACSA or anyone else, and `auto_file` is forced `false` on read as well as write.
Every change is written to the war room's decision log. The deadlines and the
paragraph references are aids taken from secondary sources: they have **not** been
checked against Bursa's or any regulator's own text, public holidays and half-day
sessions are not modelled, and the Company Secretary and counsel decide.

---

## Product invariants

These are enforced in code and covered by tests, not left to prompt discipline:

1. **No AVE.** `ave_enabled` and `methodology.ave` are pinned `false` by Pydantic
   validators that ignore whatever value is passed. Requests carrying
   `include_ave` are rejected with HTTP 422. Generated prose is regex-scanned,
   and a draft containing AVE language is discarded in favour of a safe one.
2. **Holdings never auto-publish.** `human_must_send` is forced `true` and
   `auto_publish` forced `false` on every provider path, including the agent's.
   Reaching `sent_external` requires an explicit human state transition.
3. **Evaluation weights** are fixed: outputs 15 · outtakes 25 · outcomes 35 ·
   impact 25.
4. **Exactly 3 board moves** on snapshot lock.
5. **Tabletop drafts are marked.** A simulation draft is prefixed
   `[TABLETOP — DO NOT SEND]` / `[TABLETOP — JANGAN HANTAR]` on every path, so a
   drill can never be mistaken for a sendable statement.
6. **Nothing files with a regulator.** `ListedIssuerState.auto_file` is forced
   `false`, and the Postgres migration `002` carries a check constraint for the
   same. The app records what a human decided; it does not submit.

---

## Honest limitations

Stated plainly rather than buried:

- **The in-memory store is the default.** Cloud Run containers are ephemeral, so
  drafts and war-room state reset on restart unless `NADI_USE_DB_STORE=true` and
  a database is attached. The Postgres schema and RLS policies exist in
  `schemas/migrations/`; wiring Cloud SQL is a deploy-time step.
- **Listed-issuer rules are aids, not advice.** The disclosure path, the clock windows
  and the Practice Note 2 halt note were built from secondary sources (law-firm notes,
  Bursa reprimands and news reports). Bursa's own text could not be reached while
  drafting, so paragraph numbers and exact conditions are unchecked, holidays and
  half-day sessions are not modelled, and the Company Secretary and counsel decide.
- **The scheduler has no in-process loop.** `POST /reports/schedules/run-due` is
  designed to be hit by an external timer (Cloud Scheduler), which is the
  correct shape for a scale-to-zero service but does mean nothing fires on its
  own until that trigger is configured.
- **Report delivery is not implemented.** Schedules compile the brief and record
  the run; SMTP/webhook dispatch is not wired.
- **Connectors ship with seeded data.** The RSS, social and Telegram connectors
  and their pipeline exist and are tested, but the demo runs on the Aurora /
  Jalur Kita seed rather than live ingest.
- **The live agent path needs credentials to observe.** Every layer up to the
  Google SDK boundary is tested offline, and the failure mode without
  credentials is a clean fallback rather than a crash — but the quality of a
  real Gemini-generated draft can only be judged with a live project attached.

---

## Licence

See repository settings.
