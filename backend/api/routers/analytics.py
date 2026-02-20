from __future__ import annotations

from fastapi import APIRouter

from ...config import settings
from ...models.schemas import AnalyticsResponse
from ...services.analytics_service import compute_analytics
from ...services.storage_service import load_project

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/current", response_model=AnalyticsResponse)
def analytics_current() -> AnalyticsResponse:
    project = load_project(settings.data_dir)
    return compute_analytics(project.events)
