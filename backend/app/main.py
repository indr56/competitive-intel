from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api import workspaces, competitors, pages, snapshots, changes, digests, insights, billing, events, signal_sources, prompt_clusters, ai_visibility

settings = get_settings()

app = FastAPI(
    title="Competitive Moves Intelligence",
    description="Track competitor website changes, classify them, and generate AI insights.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces.router)
app.include_router(competitors.router)
app.include_router(pages.router)
app.include_router(snapshots.router)
app.include_router(changes.router)
app.include_router(digests.router)
app.include_router(insights.router)
app.include_router(billing.router)
app.include_router(events.router)
app.include_router(signal_sources.router)
app.include_router(prompt_clusters.router)
app.include_router(ai_visibility.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
