# Hackathon rules compliance — implementation notes

Done against the actual official rules PDF (All Things Agentic Hackathon),
not assumptions. Full suite: 53/53 passing (47 prior + 6 new).

## Eligibility check (not code, a fact you confirmed)

Rules require all submitted work to have been built during the
Submission Period (Aug 3–31, 2026). You confirmed NADI's core build,
domain model, RBAC, evaluation engine, started on or after Aug 3.
Recorded here since it's the single fact this entire submission's
eligibility rests on.

## Fix 1: Model version, hard compliance requirement

Rules mandate "Gemini 3.5 or newer." The codebase was using
`gemini-2.5-flash` everywhere, direct API path, Vertex AI path, and the
config default. Verified the correct current identifier via search
(`gemini-3.5-flash`, confirmed against Google's own Vertex AI and Gen AI
SDK docs) rather than guessing. Updated every reference in
`llm_holding.py` and `config.py`, confirmed no `2.5` references remain.
Also bumped `google-genai` to `>=1.51.0`, Gemini 3 API features
specifically require that version per Google's own docs.

## Fix 2: Real Google Agent Framework, not just an SDK call

Rules mandate at least one of: Google ADK, GenAI SDK, Antigravity SDK, or
GenKit. The existing code technically satisfied this via the GenAI SDK
(a single `generate_content` call), but that scores weakly against the
judging criteria's explicit questions about state management and
properly-scoped tools.

Added `services/adk_holding_agent.py`, a real `google.adk.agents.Agent`
for the holding-statement drafting flow specifically:

- **Two real tools**, not prompt text: `get_mention_detail` (scoped to
  the specific mentions in this drafting session, not global state) and
  `verify_no_ave`, which calls the actual `reject_if_ave_requested` from
  `holding_service.py` directly, not a reimplementation, so the two can
  never silently drift apart
- **Structured output** via a Pydantic `output_schema`
  (`HoldingDraftOutput`), constraining generation directly instead of
  parsing free-text JSON and hoping it's valid
- **Defense in depth preserved**: `ave`, `auto_publish`, and
  `human_must_send` on the resulting `HoldingBrief` are hardcoded
  False/False/True regardless of what the agent produces, same discipline
  as the deterministic path and the Pydantic model's own validators
- Wired into `llm_holding.py`'s provider selection as the top-priority
  auto-selected path (tried before Vertex AI, before the direct Gemini
  key, before OpenAI, before mock), with a clean, logged fallback if it
  fails

## Fix 3: Google Cloud infrastructure — status unchanged from last time

Cloud Run Dockerfile and deploy guide already existed from the prior
session. Nothing new needed here beyond what's already documented in
`CHANGES_GCLOUD.md`, actually running `gcloud run deploy` is still a "you"
step requiring your GCP credentials.

## Verified, not just written

- Ran the full suite before and after: 47/47, then 53/53, no regressions
- Directly tested every real tool function against real seed data, the
  mention lookup returns actual 3R-flagged content
  (`mnt_tg_imbi_01`, flagged "royalty", severity "high"), and is
  confirmed JSON-serializable (a real bug was caught and fixed here, the
  first version returned a raw Pydantic `Sentiment` object which would
  have broken when ADK tried to serialize it for the model)
- `verify_no_ave` tested directly: rejects when AVE is requested with the
  exact real error message, allows when it isn't
- The agent's `build_holding_agent()` construction tested directly:
  correct model string, correct output schema, correct tool count
- **The full `draft_holding_with_adk()` was actually executed end to end**
  in this environment (no real GCP credentials exist here), and
  confirmed it fails at the correct boundary: Google's own SDK raising a
  clear "No API key was provided" error, not a crash anywhere in this
  module's own code. The traceback shows the failure occurring inside
  `google/adk/models/google_llm.py` and `google/genai/_api_client.py`,
  Google's code, not ours.
- A second real bug was found and fixed this same way: the first version
  of the mention-lookup tool referenced `m.language`, the real `Mention`
  model field is `m.lang`. Found by actually running the tool against
  real seed data, not by reading the code.

## Honest limitations

- **No live, credentialed run of the ADK agent has happened.** Everything
  above verifies the code is correct up to the exact point where real
  Google Cloud credentials would be needed. What a live run actually
  produces, the quality of the generated holding statement, whether the
  agent calls tools in a sensible order, hasn't been observed, because it
  can't be without your GCP project and credentials.
- The fallback chain (ADK → Vertex AI → direct Gemini key → OpenAI →
  mock) has only been exercised down to the mock path in this
  environment, same reason.
- No changes made to the video, architecture diagram, public repo, or
  category-specific submission content, those are the next items, not
  addressed in this pass.
