from __future__ import annotations

from fastapi import APIRouter

from ...models.schemas import AnalyticsResponse
from ...services.analytics_service import compute_analytics
from ...services.storage_service import load_project

router = APIRouter(prefix="/users/{user_id}/analytics", tags=["analytics"])


@router.get("/current", response_model=AnalyticsResponse)
def analytics_current(user_id: str) -> AnalyticsResponse:
    project = load_project(user_id)
    return compute_analytics(project.events)
