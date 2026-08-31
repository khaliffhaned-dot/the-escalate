## Inspiration

Malaysian PR desks work inside a boundary most crisis tooling ignores: **3R** — Royalty, Religion, Race. A misjudged line on any of the three isn't a bad news cycle, it's a legal and social event. The window to respond is measured in hours, and it usually opens at 2am.

The obvious agentic answer is "an agent that monitors and responds." That answer is wrong, and dangerously so. An agent that can publish on a brand's behalf into a 3R-sensitive moment is an unbounded liability. But an agent that does nothing until a human wakes up wastes the only hours that matter.

The Escalate takes the third option: **the agent does all the work up to the send, and the send is structurally unreachable to it.** Not "we prompted it not to" — structurally.

The second irritation was measurement. Most of this industry still reports AVE (Advertising Value Equivalency), a metric the Barcelona Principles have rejected since 2010 because it invents a number. We wanted a system where reporting AVE isn't a policy someone can override — it's a value the code refuses to hold.

## What it does

**Watches.** Connectors pull from news RSS, social, and public Telegram. A classifier flags 3R sensitivity with a severity and a review posture.

**Escalates.** A flagged mention opens a war room with its own queues, severity, and legal-hold state. No human triages it. It's 2am.

**Drafts.** A Google ADK agent produces a bilingual (English / Bahasa Malaysia) holding statement grounded in the specific mentions in that war room. The draft carries more than prose: information gaps it deliberately refuses to fill, a **"do not say"** list, and operational next steps with owner roles and SLAs.

**Refuses to send.** `human_must_send` is `true` and `auto_publish` is `false` on every path, forced by validators that ignore whatever the agent produced. Reaching `sent_external` requires an explicit state transition from a human holding the right permission. No code path advances it otherwise.

**Measures honestly.** Evaluation runs the AMEC Integrated Evaluation Framework — Outputs 15%, Outtakes 25%, Outcomes 35%, Impact 25% — producing a locked, hash-stamped snapshot with exactly three board moves. AVE is rejected at four separate layers.

**Reports.** Weekly executive briefs compile into a printable HTML document.

## How we built it

**A real Google ADK agent, not an SDK call.** `nadi_holding_drafter` is a `google.adk.agents.Agent` running Gemini 3.5 Flash, with two properly-scoped tools:

- `get_mention_detail` is a **closure built per request**, bound to exactly the mentions in that drafting session. The agent cannot reach a mention from another war room, workspace, or tenant — those objects aren't in the closure. Isolation is a property of construction, not a rule the model is asked to obey.
- `verify_no_ave` calls the **actual production** `reject_if_ave_requested` used by the HTTP layer, not a reimplementation, so the tool and the API can't drift apart.

Output is constrained at decode time by a Pydantic `output_schema`, not parsed out of free text and hoped over.

**Governance is in the type system.** `org_id` is on every row. Postgres row-level security policies enforce isolation at the database, and the Firestore store applies the same discipline as a composite query filter on `org_id` and `workspace_id`, so another tenant's document is never *returned* rather than filtered out in Python afterwards. A six-role RBAC matrix is checked by a FastAPI dependency on every route rather than ad hoc inside handlers.

**Four independent layers** must all fail for a statement to publish itself: the system prompt, the `verify_no_ave` tool, post-processing that hardcodes the fields regardless of model output, and Pydantic validators that coerce them anyway. Plus a state machine with no self-advancing edge.

**Stack:** Python 3.11 · FastAPI · Pydantic v2 · Google ADK · Gemini 3.5 Flash · SQLAlchemy · PostgreSQL with RLS · vanilla-JS console served from the API origin. Cloud Firestore and Cloud Run integrations are implemented but not connected to a live project — see the limitation below.

## Challenges we ran into

**A guard that lives on one branch is not a guard.** Our worst bug was architectural, not syntactic. Provider selection tries ADK first, then Vertex, then a direct key, then a deterministic fallback. The ADK branch returned its result *directly* — quietly skipping the shared post-processing every other provider passed through.

The consequence was exactly inverted from what you'd want. The **highest-priority** path — the one that runs in a real credentialed deployment — was the only path with no AVE scan of the model's own prose and, worse, no `[TABLETOP — DO NOT SEND]` marker. A training drill could return a draft typographically indistinguishable from a sendable statement. It also silently dropped `do_not_say` and `ops`, so our best path emitted *weaker* safety guidance than the fallback it outranked.

We found it by executing the path with the network stubbed out and comparing the two briefs field by field — not by reading the code. Reading it, the early `return` looks like an optimisation. Every provider now converges on one guard implementation, pinned by eight regression tests including the case where the model emits AVE language and the system must discard the draft and fall back to a safe one.

**A deploy environment that silently routed the agent away from Vertex AI.** Our Cloud Run config set only `NADI_`-prefixed variables. Those configure the app's own settings and are invisible to ADK, which builds its own `google.genai` client and resolves Vertex-vs-API-key from `GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION`. Run it one way and you get `No API key was provided` — it went to the consumer API and never touched Vertex. Run it the other and it reaches `aiplatform.googleapis.com` correctly.

The nasty part is that it fails *invisibly*: the agent errors, the fallback catches it, and you get a perfectly good deterministic draft while your headline feature isn't running at all. Only the `model_version` field tells you.

**A deployment that would have shown no product.** The console was never copied into the container and never mounted, and its API base was hardcoded to `localhost:8000` — so a deployed instance would have served JSON to a browser and called the *viewer's own* machine for data. The same bug broke a fresh clone, since the README said port 8080.

**Building for Google Cloud without a billing account.** Our GCP account carried a billing suspension from unrelated earlier work, which removed Cloud Run. Rather than drop the Google Cloud requirement, we asked which qualifying services *don't* need billing. Firestore is free on the Firebase Spark plan, with no card, and a Firebase project is a Google Cloud project. Because our routes address the store as a mapping (`store.holdings[id] = brief`), we implemented it as a write-through `MutableMapping` — and changed no route at all.

It still didn't land. The suspension turned out to cover the whole Google account, not just billing-enabled projects, so Firebase was gone too. The integration is written, tested and in the repository; there is no live project behind it. We are reporting that as a miss rather than dressing it up.

## Accomplishments that we're proud of

- An agent whose safety properties are **structural** rather than prompted — four independent layers must all fail for a statement to publish itself
- Tool scoping enforced by closure construction, so cross-tenant lookup isn't a permission check that could be missed but an object that doesn't exist
- A compliance stance (no AVE) that survives adversarial input at four layers, including a test that tampers with a database row directly and asserts the invariants are re-applied on read
- **76 tests that run fully offline**, with no credentials — the demo path is deterministic, so it can't fail live
- Bilingual EN/BM output treated as a first-class product requirement, not a translation afterthought

## What we learned

**Fallback chains are where safety properties go to die.** Each provider branch looked correct in isolation. The defect existed only in the *relationship* between branches — and specifically in the branch a reviewer is least likely to exercise, because it's the one that needs credentials to run.

**Prefer construction over instruction.** Every guard we're confident in is one the model can't reach: a closure it can't see past, a validator that overwrites its output, a state machine with no self-advancing edge. Every guard we're less confident in is one we wrote in a prompt.

**"Verified" needs a stated boundary.** We could verify the agent's wiring, tools, schema, and failure modes offline. We could not verify the prose quality of a live model run without a credentialed project. Saying exactly which is which turned out to be more useful than claiming both.

## Google Cloud usage — and one limitation, stated plainly

| Requirement | Status |
|---|---|
| Gemini 3.5 or newer | **Met** — `gemini-3.5-flash` through the Gemini API |
| A Google Agent Framework | **Met** — `google.adk.agents.Agent`, two scoped tools, Pydantic `output_schema` |
| A Google Cloud infrastructure service | **Not met** — see below |

**The limitation, stated without spin:** our Google Cloud account was already suspended over unpaid billing from unrelated earlier work, which took Cloud Run, Vertex AI and Firestore off the table for this project. There is no Google Cloud infrastructure service running behind this submission, so we do not meet the third mandatory requirement.

What we did instead of quietly dropping it: we implemented **two** Google Cloud integration paths in full, because each was reachable right up to the point where the account itself blocked us.

- **Cloud Run** is configured and documented end to end — including a deploy-environment bug we found and fixed, where the agent was being silently routed to the consumer Gemini API instead of Vertex AI. One `gcloud run deploy --source .` away.
- **Cloud Firestore** is fully implemented as a write-through store with query-level tenant scoping, covered by 10 tests, plus a script that verifies isolation against a real project. We chose it specifically because it is free on the Firebase Spark plan and needs no billing account — the account suspension, not the cost, is what stopped us.

Both are in the repository and both work. Neither has a live Google Cloud project behind it. We would rather say that plainly than imply a `.run.app` URL or a database we do not have.

## What's next for The Escalate

- Restore the Google Cloud account, then connect the Cloud Run and Firestore paths that are already written and waiting
- Real SMTP/webhook delivery for the weekly executive brief
- Live connector ingest replacing the seeded demo corpus
- SSO / SCIM for the enterprise tier
- A published evaluation set for 3R classification accuracy, since that classifier is currently the least externally-validated component
