from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nadi import AVE_ENABLED, CODENAME_EVAL, __version__
from nadi.api.routes import briefs, evaluation, mentions, reports, war_rooms
from nadi.api.store import store

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
