from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np

from manel.models import (
    PageAnalysis,
    Panel,
    PanelGroup,
    PanelType,
    ReadingDirection,
    ReadingOrder,
)

logger = logging.getLogger(__name__)


def _panel_center(panel: Panel) -> tuple[float, float]:
    x_min, y_min, x_max, y_max = panel.bbox
    return ((x_min + x_max) / 2, (y_min + y_max) / 2)


def _panel_vertical_zones(panels: list[Panel], n_zones: int = 3) -> dict[int, list[Panel]]:
    zones = defaultdict(list)
    for panel in panels:
        _, cy = _panel_center(panel)
        zone = int(cy * n_zones)
        zone = min(zone, n_zones - 1)
        zones[zone].append(panel)
    return dict(zones)


def _sort_zone_rtl(panels: list[Panel]) -> list[Panel]:
    return sorted(panels, key=lambda p: _panel_center(p)[0], reverse=True)


def _detect_overlapping_panels(panels: list[Panel]) -> list[tuple[str, str]]:
    overlaps = []
    for i, p1 in enumerate(panels):
        for j, p2 in enumerate(panels):
            if i >= j:
                continue
            x1_min, y1_min, x1_max, y1_max = p1.bbox
            x2_min, y2_min, x2_max, y2_max = p2.bbox

            inter_x = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
            inter_y = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
            inter_area = inter_x * inter_y

            if inter_area > 0:
                overlaps.append((p1.panel_id, p2.panel_id))

    return overlaps


def _detect_inserts_in_zone(panels: list[Panel]) -> list[str]:
    if len(panels) < 3:
        return []

    areas = [p.area_ratio for p in panels]
    median_area = np.median(areas)
    threshold = median_area * 0.4

    return [p.panel_id for p in panels if p.area_ratio < threshold and p.panel_type == PanelType.INSERT]


def _compute_ambiguity(panels: list[Panel], zones: dict[int, list[Panel]]) -> tuple[float, list[list[str]]]:
    if len(panels) <= 1:
        return 1.0, []

    ambiguous_regions = []

    for zone_id, zone_panels in zones.items():
        if len(zone_panels) <= 1:
            continue

        centers_x = [_panel_center(p)[0] for p in zone_panels]
        centers_y = [_panel_center(p)[1] for p in zone_panels]

        x_spread = max(centers_x) - min(centers_x)
        y_spread = max(centers_y) - min(centers_y)

        if x_spread < 0.15 and y_spread < 0.1:
            ambiguous_regions.append([p.panel_id for p in zone_panels])
            continue

        if len(zone_panels) >= 4:
            area_ratios = [p.area_ratio for p in zone_panels]
            if max(area_ratios) / (min(area_ratios) + 1e-6) < 2.0:
                ambiguous_regions.append([p.panel_id for p in zone_panels])

    base_confidence = 1.0
    base_confidence -= len(ambiguous_regions) * 0.15

    avg_confidence = np.mean([p.confidence for p in panels])
    base_confidence *= avg_confidence

    if len(panels) > 10:
        base_confidence -= 0.1

    return float(np.clip(base_confidence, 0, 1)), ambiguous_regions


def sequence_page(analysis: PageAnalysis) -> ReadingOrder:
    panels = analysis.panels
    if not panels:
        return ReadingOrder(
            page_id=analysis.page_id,
            sequence=[],
            confidence=0.0,
            reasoning=["No panels detected"],
        )

    zones = _panel_vertical_zones(panels, n_zones=3)

    sequence = []
    groups = []
    reasoning = []

    for zone_id in sorted(zones.keys()):
        zone_panels = zones[zone_id]

        inserts = _detect_inserts_in_zone(zone_panels)
        main_panels = [p for p in zone_panels if p.panel_id not in inserts]

        main_sorted = _sort_zone_rtl(main_panels)

        group_id = f"{analysis.page_id}_z{zone_id}"
        group = PanelGroup(
            group_id=group_id,
            panels=[p.panel_id for p in main_sorted],
            reading_direction=ReadingDirection.RTL,
        )
        groups.append(group)

        if inserts:
            reasoning.append(f"Zone {zone_id}: {len(main_sorted)} main panels (RTL) + {len(inserts)} insert(s)")
            insert_idx = len(main_sorted) // 2
            for insert_id in inserts:
                main_sorted.insert(insert_idx, next(p for p in zone_panels if p.panel_id == insert_id))
        else:
            reasoning.append(f"Zone {zone_id}: {len(main_sorted)} panels (RTL)")

        sequence.extend([p.panel_id for p in main_sorted])

    overlaps = _detect_overlapping_panels(panels)
    if overlaps:
        reasoning.append(f"Detected {len(overlaps)} overlapping panel pair(s)")

    confidence, ambiguous_regions = _compute_ambiguity(panels, zones)

    if ambiguous_regions:
        reasoning.append(f"{len(ambiguous_regions)} ambiguous region(s) detected")

    return ReadingOrder(
        page_id=analysis.page_id,
        sequence=sequence,
        groups=groups,
        confidence=confidence,
        ambiguous_regions=ambiguous_regions,
        reasoning=reasoning,
    )
