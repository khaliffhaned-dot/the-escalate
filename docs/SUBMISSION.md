# Devpost submission copy — The Escalate

Paste-ready text for each Devpost field. Track recommendation and the reasoning
behind it are at the bottom.

---

## Tagline

*An agentic crisis desk for Malaysian PR teams — it drafts the statement, and
structurally cannot send it.*

---

## Inspiration

Malaysian PR desks work under a constraint most crisis tooling ignores: the
**3R** boundary — Royalty, Religion, Race. A misjudged line on any of the three
is not a bad news cycle, it is a legal and social event. The window to respond
is measured in hours, and it usually opens at 2am.

The obvious agentic answer is "an agent that monitors and responds." That
answer is wrong, and dangerously so. An agent that can publish on behalf of a
brand into a 3R-sensitive moment is an unbounded liability. But an agent that
does nothing until a human is awake wastes the only hours that matter.

The Escalate takes the third option: **the agent does all the work up to the
send, and the send is structurally unreachable to it.** Not "we prompted it not
to" — structurally.

The second irritation was measurement. Most of this industry still reports AVE
(Advertising Value Equivalency), a metric the **Barcelona Principles** have
explicitly rejected since 2010 because it invents a number. We wanted a system
where reporting AVE is not a policy someone can override — it is a value the
code refuses to hold.

## What it does

**Watches.** Connectors pull from news RSS, social, and public Telegram. A
classifier flags 3R sensitivity with a severity and a review posture.

**Escalates.** A flagged mention opens a war room with its own queues,
severity, and legal-hold state.

**Drafts.** A Google ADK agent produces a bilingual (English / Bahasa Malaysia)
holding statement, grounded in the specific mentions in that war room. The draft
carries more than prose: information gaps it deliberately refuses to fill, a
**"do not say"** list, and operational next steps with owner roles and SLAs.

**Refuses to send.** `human_must_send` is `true` and `auto_publish` is `false`
on every path, forced by validators that ignore whatever the agent produced.
Reaching `sent_external` requires an explicit state transition from a human
holding the right permission. There is no code path that advances it otherwise.

**Measures honestly.** Evaluation runs the AMEC Integrated Evaluation Framework
— Outputs 15%, Outtakes 25%, Outcomes 35%, Impact 25% — and produces a locked,
hash-stamped snapshot with exactly three board moves. AVE is rejected at four
separate layers.

**Reports.** Weekly executive briefs compile into a printable HTML document,
triggered by an external scheduler.

## How we built it

**Google ADK agent, not an SDK call.** `nadi_holding_drafter` is a real
`google.adk.agents.Agent` running Gemini 3.5 Flash through the Gemini API (the
Vertex AI path is implemented and tested to the credentials boundary; it awaits
a billing-enabled project), with two properly-scoped tools:

- `get_mention_detail` is a **closure built per request**, bound to exactly the
  mentions in that drafting session. The agent cannot reach a mention from
  another war room, workspace, or tenant — those objects are not in the
  closure. Isolation is a property of construction, not a rule the model is
  asked to obey.
- `verify_no_ave` calls the **actual production** `reject_if_ave_requested`
  function used by the HTTP layer, not a reimplementation, so the tool and the
  API cannot drift apart.

Output is constrained at decode time by a Pydantic `output_schema`
(`HoldingDraftOutput`) rather than parsed out of free text.

**Stack:** Python 3.11 · FastAPI · Pydantic v2 · Google ADK · Gemini 3.5 Flash ·
SQLAlchemy · PostgreSQL with row-level security · vanilla-JS console served
from the API origin. Cloud Firestore and Cloud Run integrations are
implemented but have no live project behind them — see the limitation below.

**The Firestore store** applies the same isolation discipline, in the
query, not in application code afterwards. Every document carries `org_id` and
`workspace_id`; every read is a composite filter on both, so another tenant's
document is never returned rather than being filtered out in Python. Models
re-validate on read, which means the product invariants (`ave=False`,
`auto_publish=False`, `human_must_send=True`) are re-applied coming *out* of
the database — editing a row by hand in the Firestore console cannot
reintroduce AVE or produce a holding that publishes itself. There is a test
that performs exactly that tampering and asserts it is neutralised.

**Governance is in the type system.** `org_id` is on every row and enforced by
Postgres RLS policies, so isolation holds at the database, not just in
application queries. A six-role RBAC matrix is checked by a FastAPI dependency
on every route rather than ad hoc inside handlers.

## Challenges we ran into

**A guard that lives on one branch is not a guard.** Our worst bug was
architectural, not syntactic. Provider selection tries ADK first, then Vertex,
then a direct key, then a deterministic fallback. The ADK branch returned its
result *directly* — which quietly skipped the shared post-processing that every
other provider passed through.

The consequence was precisely inverted from what you would want. The
**highest-priority** path — the one that runs in a real credentialed deployment
— was the only path with no AVE scan of the model's own prose and, worse, no
`[TABLETOP — DO NOT SEND]` marker. A training drill could return a draft
typographically indistinguishable from a sendable statement. It also silently
dropped `do_not_say` and `ops`, so our best path emitted *weaker* safety
guidance than the fallback it outranked.

We found it by actually executing the path with the network stubbed out and
comparing the two briefs field by field, not by reading the code — reading it,
the early `return` looks like an optimisation. Every provider now converges on
one guard implementation, and eight regression tests pin that shape, including
the case where the model emits AVE language and the system must discard the
draft and fall back to a safe one.

**The deploy env silently routed the agent away from Vertex AI.** Our Cloud Run
configuration set only `NADI_`-prefixed variables. Those configure the app's
own `Settings` object and are invisible to ADK, which builds its own
`google.genai` client and resolves Vertex-vs-API-key from
`GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`.
Run it one way and you get `No API key was provided` — it went to the consumer
API and never touched Vertex; run it the other and it reaches
`aiplatform.googleapis.com` correctly. The failure is invisible from outside:
the agent errors, the fallback catches it, and you get a perfectly good
deterministic draft while the headline feature is not running. Only
`model_version` tells you.

**Making the deployment show the product.** The console was never copied into
the container and never mounted, and its API base was hardcoded to
`localhost:8000` — so a deployed instance would have served JSON to a browser
and called the *viewer's own* machine for data. The same bug broke a fresh
local clone, since the README said port 8080.

**Building for Google Cloud without a billing account.** Our GCP billing was
suspended partway through, which removed Cloud Run. Rather than drop the
Google Cloud requirement, we looked at which qualifying services do not need
billing: Firestore is free on the Firebase Spark plan, with no card, and a
Firebase project is a Google Cloud project. Because the API routes talk to the
store as a mapping (`store.holdings[id] = brief`), we could implement it as a
write-through `MutableMapping` and change no route at all.

## Accomplishments we're proud of

- An agent whose safety properties are **structural** rather than prompted —
  four independent layers must all fail for a statement to publish itself
- Tool scoping enforced by closure construction, so cross-tenant lookup is not
  a permission check that could be missed but an object that does not exist
- A compliance stance (`no AVE`) that survives adversarial input at four layers
  and is covered by tests
- 76 tests that run **fully offline**, with no credentials — the demo path is
  deterministic, so it cannot fail live on stage
- Bilingual EN/BM output treated as a first-class product requirement, not a
  translation afterthought

## What we learned

**Fallback chains are where safety properties go to die.** Each provider branch
looked correct in isolation. The defect existed only in the *relationship*
between branches — and specifically in the branch a reviewer is least likely to
exercise, because it is the one that needs credentials to run.

**Prefer construction over instruction.** Every guard we are confident in is
one the model cannot reach: a closure it cannot see past, a validator that
overwrites its output, a state machine with no self-advancing edge. Every guard
we are less confident in is one we wrote in a prompt.

**"Verified" needs a stated boundary.** We could verify the agent's wiring,
tools, schema, and failure modes offline. We could not verify the prose quality
of a live Gemini run without a credentialed project. Saying exactly which is
which turned out to be more useful than claiming both.

## Google Cloud usage — and one limitation, stated plainly

Against the three mandatory requirements:

| Requirement | Status |
|---|---|
| Gemini 3.5 or newer, via Gemini API or Vertex AI | **Met** — `gemini-3.5-flash` through the Gemini API |
| At least one Google Agent Framework | **Met** — `google.adk.agents.Agent` with two scoped tools and a Pydantic `output_schema` |
| At least one Google Cloud infrastructure service | **Not met** — see below |

**The limitation, stated without spin:** our Google Cloud account was suspended
over billing during the build, and the suspension covered the whole account —
taking Cloud Run, Vertex AI and Firebase/Firestore with it. No Google Cloud
infrastructure service is running behind this submission, so the third
mandatory requirement is not met.

Rather than quietly drop it, we implemented **two** Google Cloud paths in full,
each pursued until the account itself was the blocker:

- **Cloud Run** — configured and documented end to end in
  `DEPLOY_CLOUD_RUN.md`, including a deploy-environment bug we found and fixed
  where the agent was silently routed to the consumer Gemini API instead of
  Vertex AI. One `gcloud run deploy --source .` away.
- **Cloud Firestore** — a write-through store with query-level tenant scoping,
  10 tests, and `scripts/verify_firestore.py` to verify isolation against a
  real project. Chosen specifically because it is free on the Firebase Spark
  plan and needs no billing account; the account suspension, not the cost, is
  what stopped it.

Both are in the repository and both work. Neither has a live Google Cloud
project behind it. We would rather say so plainly than imply a `.run.app` URL
or a database we do not have.

## What's next

- Restore the Google Cloud account, then connect the Cloud Run and Firestore
  paths that are already written, corrected and waiting
- Cloud SQL attached so war-room state survives ephemeral containers
- Real SMTP/webhook delivery for the weekly executive brief
- Live connector ingest replacing the seeded demo corpus
- SSO / SCIM for the enterprise tier
- A published evaluation set for 3R classification accuracy, since that
  classifier is currently the least externally-validated component

## Built With

`python` · `fastapi` · `pydantic` · `google-adk` · `gemini` ·
`google-cloud-firestore` · `firebase` · `postgresql` · `sqlalchemy` ·
`javascript` · `docker`

---

## Track recommendation

**Primary: The Fortified Enterprise Fleet.**

This is the strongest fit and it is not close. The deepest, most defensible
work in this codebase is governance infrastructure: a six-role RBAC matrix
enforced by dependency injection, `org_id` on every row with Postgres RLS
policies, tamper-evident snapshot hashing, compliance invariants that survive
adversarial input at four layers, and an agent whose tool access is bounded by
closure construction rather than by trust. That is an enterprise-fleet story.

A judge scoring *Architectural Discipline & Tech Stack* (30%) will find more to
reward here than in either alternative.

**Why not the others:**

- *The Collaborative Partner* fits the human-must-send gate, but frames the
  system's central property as a UX pattern. The gate is not collaboration —
  it is a structural refusal, and it reads stronger as governance.
- *The Taskmaster* fits the background monitoring and scheduled briefs, but the
  autonomous surface is the weakest part of the submission — connectors run on
  seeded data and the scheduler needs an external trigger. Leading with it
  invites exactly the questions with the least satisfying answers.

**Also worth targeting: Best Architectural Design.** The guard-convergence
story — including the bug where the highest-priority path was the least
guarded, and the fix that made every provider share one implementation — is a
genuine architectural narrative with a before and after, which is unusual in a
hackathon field.
