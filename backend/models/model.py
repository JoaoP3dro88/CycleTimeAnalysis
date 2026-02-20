"""Backward-compatible module.

Your project started with an empty `model.py`. The new implementation uses
Pydantic schemas in `schemas.py`, but we re-export them here so imports like
`from backend.models.model import Project` keep working.
"""

from .schemas import (  # noqa: F401
	AnalyticsResponse,
	AnalyticsSummary,
	Event,
	Project,
	ProjectMeta,
)
