from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from nadi import AVE_ENABLED, CODENAME_EVAL, __version__
from nadi.api.routes import briefs, evaluation, mentions, reports, war_rooms
from nadi.api.store import store

# repo root: src/nadi/api/app.py -> src/nadi/api -> src/nadi -> src -> repo
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

app = FastAPI(
    title="The Escalate API",
    description="The pulse of Malaysia — social listening & AMEC Evaluation. No AVE.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mentions.router, prefix="/v1")
app.include_router(evaluation.router, prefix="/v1")
app.include_router(war_rooms.router, prefix="/v1")
app.include_router(briefs.router, prefix="/v1")
app.include_router(reports.router, prefix="/v1")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "ave_enabled": AVE_ENABLED,
        "evaluation_codename": CODENAME_EVAL,
    }


@app.get("/v1/me")
def me():
    return {
        "user": store.user.model_dump(),
        "org": store.org.model_dump(),
        "workspace": store.workspace.model_dump(),
    }


# Serve the operator console from the same origin as the API.
#
# This mount is LAST on purpose: Starlette matches routes in registration
# order, so /health, /docs, /openapi.json and every /v1/* route above still
# win, and only unmatched paths fall through to the static files. Mounting
# it at "/" is what makes the deployed Cloud Run URL show the actual product
# instead of a bare JSON 404 — the frontend is otherwise unreachable in
# deployment, since nothing else serves it.
#
# Guarded by exists() so the API still boots in contexts where only the
# installed package is present and the repo's frontend/ dir is not.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="console")
