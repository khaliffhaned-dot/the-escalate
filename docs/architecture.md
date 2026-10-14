# Architecture

The Escalate is a FastAPI service that serves both its API and its operator
console from one origin, persisting to Cloud Firestore. The interesting part is
not the request path — it is where the **guards** sit relative to the agent.

## System diagram

```mermaid
flowchart TB
    subgraph client["Operator console · vanilla JS, served at /"]
        UI["Dashboard · Mentions · Evaluation<br/>War Rooms · Holdings"]
    end

    subgraph run["FastAPI service"]
        direction TB
        RBAC["RBAC dependency<br/>X-Nadi-Role → permission matrix"]

        subgraph ingest["Ingest"]
            CONN["Connectors<br/>RSS · social · Telegram"]
            PIPE["Pipeline"]
            CLS["3R classifier<br/>royalty · religion · race"]
        end

        subgraph crisis["Crisis path"]
            WR["War room<br/>severity · posture · queues"]
            SEL["Provider selection<br/>llm_holding.py"]
            GUARD["Text guards<br/>AVE regex · TABLETOP marker"]
            SM["State machine<br/>draft → legal_review → approved → sent_external"]
        end

        subgraph measure["Measurement path"]
            EVAL["AMEC IEF scoring<br/>15 / 25 / 35 / 25"]
            SNAP["Locked snapshot<br/>+ exactly 3 board moves"]
            REP["Executive brief<br/>compile → HTML"]
        end
    end

    subgraph google["Google Cloud"]
        ADK["ADK Agent<br/>nadi_holding_drafter"]
        GEM["Gemini 3.5 Flash"]
        FS[("Cloud Firestore<br/>org_id + workspace_id<br/>on every document")]
    end

    HUMAN(["Human operator<br/>the only path to send"])
    CS["Cloud Scheduler<br/>external timer"]

    UI --> RBAC
    RBAC --> ingest & crisis & measure
    CONN --> PIPE --> CLS
    CLS -->|"3R flag raised"| WR
    CLS --> EVAL
    WR --> SEL
    SEL --> ADK
    ADK <-->|"tool calls"| GEM
    ADK -->|"HoldingDraftOutput"| GUARD
    SEL -.->|"no credentials,<br/>or guard rejects"| GUARD
    GUARD --> SM
    SM -->|"sent_external<br/>requires a human"| HUMAN
    EVAL --> SNAP --> REP
    CS -->|"POST /reports/schedules/run-due"| REP
    SM <-->|"write-through"| FS
    WR <--> FS
    SNAP --> FS

    classDef guard fill:#7f1d1d,stroke:#ef4444,color:#fff
    classDef gcp fill:#1e3a5f,stroke:#4285f4,color:#fff
    classDef human fill:#14532d,stroke:#22c55e,color:#fff
    class GUARD,SM guard
    class ADK,GEM,FS gcp
    class HUMAN human
```

## The agent, in detail

The holding-statement drafter is a real `google.adk.agents.Agent`, not a single
`generate_content` call. Two things make it worth the extra machinery:

```mermaid
flowchart LR
    REQ["Draft request<br/>mentions + locale + tabletop"]

    subgraph agent["nadi_holding_drafter"]
        LLM["Gemini 3.5 Flash"]
        T1["get_mention_detail()<br/><i>closure bound to THIS<br/>request's mentions</i>"]
        T2["verify_no_ave()<br/><i>calls the real<br/>reject_if_ave_requested</i>"]
    end

    OUT["HoldingDraftOutput<br/>Pydantic output_schema"]
    G1{"AVE regex<br/>on generated prose"}
    G2["TABLETOP marker"]
    G3["Pydantic validators<br/>ave=False · auto_publish=False<br/>human_must_send=True"]
    BRIEF["HoldingBrief"]
    FALL["Deterministic draft"]

    REQ --> LLM
    LLM <--> T1
    LLM <--> T2
    LLM --> OUT --> G1
    G1 -->|"clean"| G2 --> G3 --> BRIEF
    G1 -->|"AVE detected"| FALL --> G3

    classDef guard fill:#7f1d1d,stroke:#ef4444,color:#fff
    class G1,G2,G3 guard
```

**Tools are scoped, not global.** `get_mention_detail` is a closure built per
request, bound to exactly the mentions in that drafting session. The agent
cannot look up a mention belonging to another war room, another workspace, or
another tenant, because those objects are not in the closure. Isolation is a
property of construction rather than a rule the model is asked to follow.

**`verify_no_ave` calls the production function.** It invokes the same
`reject_if_ave_requested` used by the HTTP layer — not a reimplementation — so
the tool and the API can never drift apart.

**The output schema constrains generation.** `HoldingDraftOutput` is passed as
ADK's `output_schema`, so the model is constrained at decode time rather than
producing free text that is parsed and hoped over.

## Listed-issuer war rooms

A war room can carry a `ListedIssuerState` (`domain/listed.py`): the disclosure
assessment, the insider lock, twelve regulatory clocks and the halt record. The logic
is pure functions in `services/listed_issuer.py`, so every rule is tested without a
store or a clock; `api/routes/listed.py` is a thin wrapper.

Three boundaries matter:

- **It records and prompts.** There is no path that files with Bursa or any regulator,
  and `auto_file` is forced `false` the same way `auto_publish` is on a holding.
- **Routes write the room back.** `FirestoreDocMap` returns a fresh copy on every read,
  so mutating the object a route read is lost unless it is assigned back. The listed
  routes always do `store.war_rooms[id] = wr`, and a test drives them against a store
  that returns copies.
- **The holding guard runs after the model.** `apply_listed_guard` adds the Bursa-first
  rules to the brief whichever provider produced it, in the same place the AVE scan and
  the tabletop marker are applied, so they do not rely on the prompt being followed.

Storage: one nullable JSON column `listed` on `war_rooms`
(`schemas/migrations/002_war_room_listed_issuer.sql`). The row-level-security policy
from `001` already covers the whole row.

## Why the guards sit outside the agent

Every provider path — ADK, Vertex AI, direct Gemini, OpenAI, deterministic —
converges on one guard implementation before a `HoldingBrief` exists.

This was not always true, and the failure is instructive. The ADK branch
originally returned its brief directly, which skipped the shared guards. Because
ADK is the *highest-priority* provider, the path most likely to run in a
credentialed deployment was the one path with no AVE scan of the model's own
prose and no `[TABLETOP — DO NOT SEND]` marker — meaning a training drill could
return a draft indistinguishable from a sendable statement. It also dropped
`do_not_say` and `ops`, so the best path produced weaker safety guidance than
the fallback it outranked.

The lesson generalised: **a guard that lives on one branch is not a guard.**
`tests/test_adk_guards.py` now pins this shape, including the case where the
model emits AVE language and the system must discard it and fall back to a safe
draft rather than pass it through.

## Defence in depth on the send gate

Four independent layers must all fail for a statement to publish itself:

| Layer | Mechanism |
|-------|-----------|
| Prompt | System prompt forbids AVE and auto-publish |
| Tool | `verify_no_ave` lets the agent check before finalising |
| Post-process | Regex scan + hardcoded field assignment, ignoring model output |
| Model | Pydantic `field_validator`s coerce `ave`/`auto_publish` to `False` and `human_must_send` to `True` regardless of input |

Plus the state machine: `sent_external` is reachable only from `approved`, and
only by an explicit transition request from a role holding the permission.
There is no code path that advances that state on its own.

## Data isolation

`org_id` is on every row. `schemas/migrations/001_initial_schema_and_rls.sql`
defines Postgres row-level security policies so isolation is enforced by the
database, not only by application queries. The RBAC matrix in
`domain/rbac.py` gates the six roles against named permissions
(`ws.reports.run`, `ws.brief.run`, …), checked by a FastAPI dependency on every
route rather than ad hoc inside handlers.

## Deployment

Two paths, because they have different prerequisites.

**Firestore — no billing account.** Cloud Run requires billing enabled;
Firestore does not, being free on the Firebase Spark plan. Since the routes
address the store as a mapping (`store.holdings[id] = brief`), the Firestore
backend is a write-through `MutableMapping` and no route changed. Isolation is
a composite query filter on `org_id` and `workspace_id`, so a foreign document
is never returned rather than filtered out afterwards, and models re-validate
on read so the invariants are re-applied coming *out* of the database.

**Cloud Run — needs billing.**

```
gcloud run deploy --source .
        │
        ├── Cloud Build builds the image remotely (no local Docker)
        ├── Container: python:3.12-slim, uvicorn binding $PORT
        ├── Serves API + console on one origin
        └── ADC → Vertex AI (service account needs Vertex AI User)
```

Scale-to-zero (`--min-instances 0`) is deliberate: a PR desk's crisis tooling is
idle most of the time, and the state that matters belongs in Firestore rather
than in a warm container.

Either way the store selection is logged at startup, so which backend is live
is never a guess — and an unreachable Firestore degrades to the in-memory store
rather than refusing to boot. Losing persistence is bad; failing to start
during a crisis is worse.
