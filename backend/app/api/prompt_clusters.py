"""API endpoints for prompt clustering system."""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import MonitoredPrompt, PromptCluster
from app.schemas.schemas import (
    ClusteringResultRead,
    MonitoredPromptCreate,
    MonitoredPromptRead,
    PromptClusterRead,
)

router = APIRouter(tags=["prompt-clusters"])


# ── Prompts ──


@router.post(
    "/api/workspaces/{workspace_id}/prompts",
    response_model=MonitoredPromptRead,
    status_code=201,
)
def create_prompt(
    workspace_id: uuid.UUID,
    payload: MonitoredPromptCreate,
    db: Session = Depends(get_db),
):
    """Add a new monitored prompt to a workspace."""
    from app.services.prompt_clustering import add_prompt_to_workspace

    try:
        prompt = add_prompt_to_workspace(db, str(workspace_id), payload.raw_text)
    except Exception as exc:
        if "uq_monitored_prompt_ws_text" in str(exc):
            raise HTTPException(status_code=409, detail="Prompt already exists in this workspace")
        raise
    return prompt


@router.get(
    "/api/workspaces/{workspace_id}/prompts",
    response_model=List[MonitoredPromptRead],
)
def list_prompts(
    workspace_id: uuid.UUID,
    cluster_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List monitored prompts for a workspace."""
    query = db.query(MonitoredPrompt).filter(
        MonitoredPrompt.workspace_id == workspace_id
    )
    if cluster_id:
        query = query.filter(MonitoredPrompt.cluster_id == cluster_id)

    return (
        query.order_by(MonitoredPrompt.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.delete("/api/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a monitored prompt."""
    prompt = db.query(MonitoredPrompt).filter(MonitoredPrompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    db.delete(prompt)
    db.commit()


# ── Clusters ──


@router.get(
    "/api/workspaces/{workspace_id}/prompt-clusters",
    response_model=List[PromptClusterRead],
)
def list_clusters(
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """List prompt clusters for a workspace (with their member prompts)."""
    clusters = (
        db.query(PromptCluster)
        .filter(PromptCluster.workspace_id == workspace_id)
        .order_by(PromptCluster.created_at.desc())
        .all()
    )
    return clusters


@router.get(
    "/api/prompt-clusters/{cluster_id}",
    response_model=PromptClusterRead,
)
def get_cluster(cluster_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a single prompt cluster with its prompts."""
    cluster = db.query(PromptCluster).filter(PromptCluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster


@router.post(
    "/api/workspaces/{workspace_id}/prompt-clusters/run",
    response_model=ClusteringResultRead,
)
def run_clustering(
    workspace_id: uuid.UUID,
    threshold: float = Query(default=0.65, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """Run prompt clustering for a workspace."""
    from app.services.prompt_clustering import cluster_prompts

    result = cluster_prompts(db, str(workspace_id), threshold=threshold)
    return result


@router.delete("/api/prompt-clusters/{cluster_id}", status_code=204)
def delete_cluster(cluster_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete a prompt cluster (prompts remain, just unlinked)."""
    cluster = db.query(PromptCluster).filter(PromptCluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    # Unlink prompts first
    for p in cluster.prompts:
        p.cluster_id = None
    db.delete(cluster)
    db.commit()
