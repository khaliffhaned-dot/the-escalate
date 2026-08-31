# Implementation Plan - Report Scheduler & Weekly AMEC Executive Brief Generator

Build an automated report scheduler and executive briefing engine for PR desks, compiling AMEC Integrated Evaluation Framework (IEF) snapshots, 3R audits, East MY geographic metrics, and 3 Board Moves into a responsive HTML email and downloadable executive report.

## User Review Required

> [!IMPORTANT]
> All generated reports are certified **Barcelona Principles 4.0** compliant:
> - Zero AVE/EMV/PR value calculations.
> - Multi-dimensional contribution score across Outputs (15%), Outtakes (25%), Outcomes (35%), and Impact (25%).
> - Explicit human governance attribution and tamper-evident snapshot hash.

---

## Proposed Changes

### Reporting Engine
#### [NEW] [`src/nadi/services/reporting_service.py`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/src/nadi/services/reporting_service.py)
- `build_executive_report`: Compiles mentions, evaluation snapshots, active war rooms, and holdings into a cohesive executive report data structure.
- `generate_report_html`: Renders a standalone responsive HTML email / printable PDF document with charts, ladder stage progress, 3R risk summary, East Malaysia distribution, and board moves.

---

### Report Scheduler
#### [NEW] [`src/nadi/services/scheduler.py`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/src/nadi/services/scheduler.py)
- `ReportScheduler`: Async scheduler managing weekly and periodic report generation jobs, supporting recipient email lists and webhook delivery.

---

### API Routes
#### [NEW] [`src/nadi/api/routes/reports.py`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/src/nadi/api/routes/reports.py)
- `POST /v1/workspaces/{ws_id}/reports/generate`: Generates an on-demand executive brief.
- `GET /v1/workspaces/{ws_id}/reports/preview`: Renders HTML document directly for browser preview or print-to-PDF.
- `POST /v1/workspaces/{ws_id}/reports/schedule`: Registers or updates report schedules.
- `GET /v1/workspaces/{ws_id}/reports/schedules`: Lists workspace report schedules.

#### [MODIFY] [`src/nadi/api/app.py`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/src/nadi/api/app.py)
- Include `reports.router` in FastAPI application.

---

### Frontend UI Enhancement
#### [MODIFY] [`frontend/index.html`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/frontend/index.html) & [`frontend/app.js`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/frontend/app.js)
- Add "Executive Brief / Export Report" button in the Evaluation page.
- Add report preview modal with direct "Print / Save PDF" and "Schedule Weekly Email" controls.

---

### Tests
#### [NEW] [`tests/test_reporting_and_scheduler.py`](file:///C:/Users/Mkhal/OneDrive/Documents/Desktop/nadi/tests/test_reporting_and_scheduler.py)
- Test report data compilation from seed data.
- Test HTML rendering and AVE rejection checks.
- Test report scheduler registration and job execution.
- Test `/reports/generate`, `/reports/preview`, and `/reports/schedule` endpoints.

---

## Verification Plan

### Automated Tests
- Run `pytest` via `.venv\Scripts\pytest.exe` to ensure all 23 existing tests and new reporting tests pass.

### Manual Verification
- Test `GET /v1/workspaces/ws_aurora/reports/preview` in browser.
- Verify that opening the Executive Brief modal in the frontend displays the full AMEC evaluation breakdown and 3 board moves.
