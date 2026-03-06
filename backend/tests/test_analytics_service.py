"""Unit tests for analytics_service.py.

Run with:
    cd CycleTimeAnalysis
    backend\\.venv\\Scripts\\pytest backend/tests/ -v
"""
from __future__ import annotations

import pytest

from backend.models.schemas import Event
from backend.services.analytics_service import (
    compute_analytics,
    compute_gantt,
    compute_heatmap,
    compute_object_analysis,
    compute_summary,
    compute_value_by_category,
    compute_yamazumi,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_event(**kwargs) -> Event:
    defaults = dict(
        operation="Op A",
        start_frame=0,
        end_frame=30,
        duration=1.0,
        category="TAV",
        object="Mão Direita",
        resource="HD1",
    )
    defaults.update(kwargs)
    return Event(**defaults)


SAMPLE_EVENTS = [
    make_event(operation="Pegar peça",   start_frame=0,   end_frame=60,  duration=2.0,  category="TAV",  object="Mão Direita",   resource="HD1"),
    make_event(operation="Posicionar",   start_frame=60,  end_frame=90,  duration=1.0,  category="NNVA", object="Mão Esquerda",  resource="HE1"),
    make_event(operation="Aparafusar",   start_frame=90,  end_frame=150, duration=2.0,  category="TAV",  object="Mão Direita",   resource="HD1"),
    make_event(operation="Inspecionar",  start_frame=150, end_frame=180, duration=1.0,  category="TNAV", object="Mão Direita",   resource="HD1"),
    make_event(operation="Descansar",    start_frame=180, end_frame=210, duration=1.0,  category="",     object="Mão Esquerda",  resource="HE1"),
]


# ─── compute_summary ─────────────────────────────────────────────────────────

class TestComputeSummary:
    def test_empty_events(self):
        result = compute_summary([])
        assert result.total_time_s == 0.0
        assert result.tav_time_s == 0.0
        assert result.waste_percent == 0.0
        assert result.total_operations == 0

    def test_total_time(self):
        result = compute_summary(SAMPLE_EVENTS)
        assert result.total_time_s == pytest.approx(7.0)

    def test_tav_time(self):
        result = compute_summary(SAMPLE_EVENTS)
        assert result.tav_time_s == pytest.approx(4.0)

    def test_waste_percent(self):
        result = compute_summary(SAMPLE_EVENTS)
        # TAV = 4s out of 7s → waste = 100 - (4/7 * 100) ≈ 42.857%
        assert result.waste_percent == pytest.approx(100.0 - (4.0 / 7.0 * 100.0), rel=1e-4)

    def test_total_operations(self):
        result = compute_summary(SAMPLE_EVENTS)
        assert result.total_operations == 5

    def test_all_tav_no_waste(self):
        events = [make_event(category="TAV", duration=1.0) for _ in range(3)]
        result = compute_summary(events)
        assert result.waste_percent == pytest.approx(0.0)

    def test_all_nnva_full_waste(self):
        events = [make_event(category="NNVA", duration=1.0) for _ in range(3)]
        result = compute_summary(events)
        assert result.waste_percent == pytest.approx(100.0)


# ─── compute_value_by_category ───────────────────────────────────────────────

class TestComputeValueByCategory:
    def test_returns_all_categories(self):
        result = compute_value_by_category(SAMPLE_EVENTS)
        cats = {item.category for item in result}
        assert cats == {"TAV", "NNVA", "TNAV", ""}

    def test_tav_duration(self):
        result = compute_value_by_category(SAMPLE_EVENTS)
        tav = next(i for i in result if i.category == "TAV")
        assert tav.duration_s == pytest.approx(4.0)

    def test_empty_events(self):
        result = compute_value_by_category([])
        assert result == []


# ─── compute_yamazumi ────────────────────────────────────────────────────────

class TestComputeYamazumi:
    def test_groups_by_resource_and_category(self):
        result = compute_yamazumi(SAMPLE_EVENTS)
        keys = {(item.resource, item.category) for item in result}
        assert ("HD1", "TAV") in keys
        assert ("HE1", "NNVA") in keys

    def test_hd1_tav_duration(self):
        result = compute_yamazumi(SAMPLE_EVENTS)
        hd1_tav = next(i for i in result if i.resource == "HD1" and i.category == "TAV")
        assert hd1_tav.duration_s == pytest.approx(4.0)

    def test_empty_events(self):
        assert compute_yamazumi([]) == []


# ─── compute_heatmap ─────────────────────────────────────────────────────────

class TestComputeHeatmap:
    def test_matrix_shape(self):
        result = compute_heatmap(SAMPLE_EVENTS)
        assert len(result.matrix) == len(result.operations)
        for row in result.matrix:
            assert len(row) == len(result.objects)

    def test_operations_sorted(self):
        result = compute_heatmap(SAMPLE_EVENTS)
        assert result.operations == sorted(result.operations)

    def test_objects_sorted(self):
        result = compute_heatmap(SAMPLE_EVENTS)
        assert result.objects == sorted(result.objects)

    def test_matrix_values_non_negative(self):
        result = compute_heatmap(SAMPLE_EVENTS)
        for row in result.matrix:
            for val in row:
                assert val >= 0.0

    def test_matrix_sum_equals_total_duration(self):
        result = compute_heatmap(SAMPLE_EVENTS)
        total = sum(val for row in result.matrix for val in row)
        assert total == pytest.approx(sum(e.duration for e in SAMPLE_EVENTS), rel=1e-4)

    def test_empty_events(self):
        result = compute_heatmap([])
        assert result.operations == []
        assert result.objects == []
        assert result.matrix == []


# ─── compute_gantt ───────────────────────────────────────────────────────────

class TestComputeGantt:
    def test_returns_one_item_per_event(self):
        result = compute_gantt(SAMPLE_EVENTS)
        assert len(result) == len(SAMPLE_EVENTS)

    def test_fields_preserved(self):
        ev = SAMPLE_EVENTS[0]
        result = compute_gantt([ev])
        item = result[0]
        assert item.operation == ev.operation
        assert item.object == ev.object
        assert item.resource == ev.resource
        assert item.category == ev.category
        assert item.start_frame == ev.start_frame
        assert item.end_frame == ev.end_frame
        assert item.duration_s == pytest.approx(ev.duration)

    def test_empty_events(self):
        assert compute_gantt([]) == []


# ─── compute_object_analysis ─────────────────────────────────────────────────

class TestComputeObjectAnalysis:
    def test_returns_one_item_per_unique_object(self):
        result = compute_object_analysis(SAMPLE_EVENTS)
        objects = {item.object for item in result}
        expected = {"Mão Direita", "Mão Esquerda"}
        assert objects == expected

    def test_total_duration_for_mao_direita(self):
        result = compute_object_analysis(SAMPLE_EVENTS)
        md = next(i for i in result if i.object == "Mão Direita")
        # Pegar peça (2) + Aparafusar (2) + Inspecionar (1) = 5s
        assert md.total_duration_s == pytest.approx(5.0)

    def test_tav_duration_for_mao_direita(self):
        result = compute_object_analysis(SAMPLE_EVENTS)
        md = next(i for i in result if i.object == "Mão Direita")
        # Pegar peça (2 TAV) + Aparafusar (2 TAV) = 4s
        assert md.tav_duration_s == pytest.approx(4.0)

    def test_waste_percent_for_mao_direita(self):
        result = compute_object_analysis(SAMPLE_EVENTS)
        md = next(i for i in result if i.object == "Mão Direita")
        # TAV=4 / total=5 → waste = 100 - 80 = 20%
        assert md.waste_percent == pytest.approx(20.0, rel=1e-4)

    def test_event_count(self):
        result = compute_object_analysis(SAMPLE_EVENTS)
        md = next(i for i in result if i.object == "Mão Direita")
        assert md.event_count == 3

    def test_empty_events(self):
        assert compute_object_analysis([]) == []


# ─── compute_analytics (integration) ─────────────────────────────────────────

class TestComputeAnalytics:
    def test_all_fields_present(self):
        result = compute_analytics(SAMPLE_EVENTS)
        assert result.summary is not None
        assert isinstance(result.value_by_category, list)
        assert isinstance(result.yamazumi, list)
        assert result.heatmap is not None
        assert isinstance(result.gantt, list)
        assert isinstance(result.object_analysis, list)

    def test_empty_events_does_not_raise(self):
        result = compute_analytics([])
        assert result.summary.total_operations == 0
        assert result.gantt == []
        assert result.object_analysis == []
