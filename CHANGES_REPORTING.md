# Report Scheduler & Executive Brief — implementation notes

Implemented against the real current codebase (23 existing tests, LLM
holding drafting, live connectors, Postgres/RLS layer, working frontend),
not an earlier stale copy. Full suite: 45/45 passing (23 original + 22 new).

## What was built, per the implementation plan

- `services/reporting_service.py` — `build_executive_report` (compiles a
  locked snapshot + mentions + war rooms + holdings) and
  `generate_report_html` (print-styled HTML)
- `services/scheduler.py` — `ReportScheduler`, weekly schedule registry
- `api/routes/reports.py` — generate, preview, schedule, schedules,
  schedules/run-due
- `db/models.py` — `ReportScheduleDB` for optional persistence
- `frontend/index.html` + `app.js` — Executive Brief button, preview
  modal, print/save, schedule form
- `tests/test_reporting_and_scheduler.py` — 22 tests

## Gaps flagged before implementation, and how each was handled

1. **No permission gating specified in the plan.** `ws.reports.run`
   already existed in the RBAC matrix (ws_admin, editor) but nothing
   checked it anywhere, same shape of gap as two earlier fixes. Every
   route in `reports.py` now calls `need(ctx, WS_REPORTS_RUN)` explicitly.
   Verified live: viewer and analyst both 403, editor 200.

2. **Scheduler persistence depended on infrastructure that didn't exist
   when the plan was written.** It does now, this codebase already has a
   real Postgres/RLS layer (`db/`, `NADI_USE_DB_STORE`). Added
   `ReportScheduleDB` so schedule configs survive a restart when that flag
   is on. When it's off (today's default), schedules still live only in
   process memory, the API's `persistent: false` field says so honestly
   rather than implying otherwise, and the frontend surfaces that note
   directly in the schedule confirmation message.

3. **"HTML email / printable PDF document" was ambiguous.** Resolved as:
   this generates print-styled HTML, not a PDF file. No PDF library is
   used or added. Route docstrings, the API's own response, and the
   rendered HTML footer all say this explicitly. The frontend's
   "Print / Save PDF" button calls the browser's own print dialog on the
   preview iframe, it does not claim to hand back a `.pdf`.

4. **Webhook delivery needed an SSRF note.** `validate_webhook_url`
   rejects localhost, private, link-local, reserved, and multicast address
   ranges (including the cloud metadata endpoint, 169.254.169.254) before
   a webhook URL is ever stored. This is a denylist, not a full allowlist,
   treat it as a floor. Verified live and covered by parametrized tests.

## Verified live, not just by reading code

- Report generation returns real compiled data from the actual seed
  (contribution score, exactly 3 moves, real 3R/East MY breakdowns)
- Permission gating tested against a running server: viewer 403, analyst
  403, editor 200
- The `/reports/preview` HTML response tested live: 200, `text/html`
  content-type, real title, AVE-disclosure banner present
- SSRF guard tested live: `127.0.0.1` and the cloud metadata IP both
  rejected at the route with 422, valid registration succeeds
- The served `index.html` and `app.js` were fetched over HTTP exactly as
  a browser would load them, confirmed the button markup and the modal
  function are actually present in what gets served, and the exact
  network calls the modal's JS makes (the iframe preview fetch, the
  schedule POST) were replayed against the real running backend with
  identical payloads
- No Chrome browser was connected in this environment, so an actual
  visual click-through in a real browser window was not possible here,
  everything above verifies the served bytes and the exact request/response
  pairs the UI would produce, not a live screenshot of the modal open

## Not addressed here, separate from this feature

- This branch forked before the earlier RBAC separation-of-duties fix
  (holding approve/send split) and the war-room close policy fix, neither
  is present in this codebase. Left untouched since it's a separate scope
  decision from the report scheduler, flagged for you to decide on
  separately.
- No actual SMTP/webhook delivery is implemented. `schedules/run-due`
  compiles the report and records that a run happened; sending it to the
  recipients or webhook is next-step work.
- No background loop starts automatically. `run_due()` needs an external
  periodic trigger (cron, APScheduler, your host's scheduled-task feature)
  hitting `POST /reports/schedules/run-due`, this deliberately avoids
  adding a second unmanaged scheduler loop to the FastAPI process.
