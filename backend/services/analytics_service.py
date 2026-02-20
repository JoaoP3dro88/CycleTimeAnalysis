from __future__ import annotations

from collections import defaultdict

from ..models.schemas import (
    AnalyticsResponse,
    AnalyticsSummary,
    Event,
    HeatmapResponse,
    ValueByCategoryItem,
    YamazumiItem,
)


def compute_summary(events: list[Event]) -> AnalyticsSummary:
    total_time = sum(e.duration for e in events)
    tav_time = sum(e.duration for e in events if e.category == "TAV")
    waste_percent = 0.0
    if total_time > 0:
        waste_percent = 100.0 - ((tav_time / total_time) * 100.0)

    return AnalyticsSummary(
        total_time_s=round(total_time, 6),
        tav_time_s=round(tav_time, 6),
        waste_percent=round(waste_percent, 6),
        total_operations=len(events),
    )


def compute_value_by_category(events: list[Event]) -> list[ValueByCategoryItem]:
    agg: dict[str, float] = defaultdict(float)
    for e in events:
        agg[e.category or ""] += e.duration

    return [
        ValueByCategoryItem(category=cat, duration_s=round(dur, 6))
        for cat, dur in sorted(agg.items(), key=lambda x: x[0])
    ]


def compute_yamazumi(events: list[Event]) -> list[YamazumiItem]:
    agg: dict[tuple[str, str], float] = defaultdict(float)
    for e in events:
        agg[(e.resource, e.category or "")] += e.duration

    out: list[YamazumiItem] = []
    for (resource, category), dur in sorted(agg.items(), key=lambda x: (x[0][0], x[0][1])):
        out.append(YamazumiItem(resource=resource, category=category, duration_s=round(dur, 6)))
    return out


def compute_heatmap(events: list[Event]) -> HeatmapResponse:
    # operation x object -> sum(duration)
    operations = sorted({e.operation for e in events})
    objects = sorted({e.object for e in events})

    op_index = {op: i for i, op in enumerate(operations)}
    obj_index = {obj: j for j, obj in enumerate(objects)}

    matrix = [[0.0 for _ in objects] for _ in operations]
    for e in events:
        matrix[op_index[e.operation]][obj_index[e.object]] += e.duration

    matrix = [[round(v, 6) for v in row] for row in matrix]

    return HeatmapResponse(operations=operations, objects=objects, matrix=matrix)


def compute_analytics(events: list[Event]) -> AnalyticsResponse:
    return AnalyticsResponse(
        summary=compute_summary(events),
        value_by_category=compute_value_by_category(events),
        yamazumi=compute_yamazumi(events),
        heatmap=compute_heatmap(events),
    )
