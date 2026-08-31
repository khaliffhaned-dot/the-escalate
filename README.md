# The Escalate

*(internal package name remains `nadi`, imports and CLI commands below are unchanged)*

Production-oriented **Python** scaffold for Malaysian social listening + **AMEC / Barcelona Principles 4.0** Evaluation, with a real Google ADK agent that drafts crisis holding statements and structurally cannot send one alone.

- **No AVE** (enforced in models, API, holdings)
- Evaluation codename: `berry-bison-yonder-cabin`
- War room + holding statements (human must send)
- Tenant/RBAC permission matrix
- Aurora / Jalur Kita demo seed

This is a **backend API scaffold**, not full live ingest. Wire connectors next.

## Quick start

```bash
cd nadi
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
uvicorn nadi.api.app:app --reload --port 8080
```

Open: http://127.0.0.1:8080/docs

Health: `GET /health`

## Auth (demo)

Pass header:

```
X-Nadi-Role: ws_admin
```

Roles: `ws_admin` | `editor` | `analyst` | `viewer` | `org_admin` | `org_auditor`

## Key routes

| Method | Path | Notes |
|--------|------|--------|
| GET | `/v1/workspaces/{ws}/mentions` | Seed mentions |
| GET | `/v1/workspaces/{ws}/evaluation` | Live evaluation view |
| POST | `/v1/workspaces/{ws}/evaluation/lock` | Lock snapshot (rejects `include_ave`) |
| GET | `/v1/workspaces/{ws}/war-rooms` | Crisis canvas |
| POST | `/v1/workspaces/{ws}/briefs` | `{ "kind": "holding", "mention_ids": [...] }` |
| POST | `/v1/workspaces/{ws}/holdings/{id}/transition` | draft → approved → sent_external |

Demo workspace id: `ws_aurora`

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

## Layout

```
src/nadi/
  domain/     enums, models, rbac
  services/   contribution, evaluation, war_room, holding
  api/        FastAPI app + routes
  data/       Aurora seed
  prompts/    holding system prompt (Barcelona 4.0)
```

## Product invariants

1. `ave_enabled` / `methodology.ave` always `false`
2. Holdings never auto-publish
3. Evaluation weights: outputs 15 · outtakes 25 · outcomes 35 · impact 25
4. Exactly 3 board moves on lock

## Next build steps

1. Postgres + RLS (`org_id` on every row)
2. Live connectors (news, X, Meta, Telegram public)
3. LLM Brief behind the holding system prompt
4. Report scheduler + weekly email HTML
5. SSO / SCIM for Enterprise tier
