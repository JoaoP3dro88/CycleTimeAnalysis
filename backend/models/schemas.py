from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class Category(str, Enum):
    TAV = "TAV"
    NNVA = "NNVA"
    TNAV = "TNAV"
    EMPTY = ""


class Event(BaseModel):
    operation: str = Field(default="Nova Operação", min_length=1)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    duration: float = Field(default=0.0, ge=0.0)
    category: str = Field(default="")
    object: str = Field(default="Objeto")
    resource: str = Field(default="Recurso")

    @model_validator(mode="after")
    def _frames_and_duration(self) -> "Event":
        if self.end_frame <= self.start_frame:
            raise ValueError("end_frame must be greater than start_frame")
        return self


class RoiPoint(BaseModel):
    x: float
    y: float


class Roi(BaseModel):
    name: str = ""
    points: list[RoiPoint] = Field(default_factory=list)
    leftCategory: str = ""
    rightCategory: str = ""


class ProjectMeta(BaseModel):
    video_path: Optional[str] = None
    video_filename: Optional[str] = None   # basename of the last loaded video
    fps: float = Field(default=30.0, gt=0)
    total_frames: int = Field(default=0, ge=0)
    takt_time: float = Field(default=10.0, ge=0)


class Project(BaseModel):
    meta: ProjectMeta = Field(default_factory=ProjectMeta)
    events: list[Event] = Field(default_factory=list)
    rois: list[Roi] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AnalyticsSummary(BaseModel):
    total_time_s: float
    tav_time_s: float
    waste_percent: float
    total_operations: int


class ValueByCategoryItem(BaseModel):
    category: str
    duration_s: float


class YamazumiItem(BaseModel):
    resource: str
    category: str
    duration_s: float


class HeatmapResponse(BaseModel):
    operations: list[str]
    objects: list[str]
    matrix: list[list[float]]


class AnalyticsResponse(BaseModel):
    summary: AnalyticsSummary
    value_by_category: list[ValueByCategoryItem]
    yamazumi: list[YamazumiItem]
    heatmap: HeatmapResponse
    # gantt and object analysis can be added next
