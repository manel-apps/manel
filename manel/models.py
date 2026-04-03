from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PanelType(str, Enum):
    MAIN = "main"
    INSERT = "insert"
    DOUBLE_PAGE = "double_page"
    ARTISTIC = "artistic"
    UNKNOWN = "unknown"


class ReadingDirection(str, Enum):
    RTL = "rtl"
    LTR = "ltr"
    AMBIGUOUS = "ambiguous"


class Panel(BaseModel):
    panel_id: str
    bbox: tuple[float, float, float, float] = Field(
        description="(x_min, y_min, x_max, y_max) normalized 0-1"
    )
    panel_type: PanelType = PanelType.UNKNOWN
    area_ratio: float = Field(
        description="Panel area relative to page area"
    )
    has_text: bool = False
    text_content: Optional[str] = None
    visual_weight: float = Field(
        default=0.5,
        description="Estimated visual importance 0-1"
    )
    confidence: float = Field(
        default=1.0,
        description="Detection confidence 0-1"
    )
    metadata: dict = Field(default_factory=dict)


class PanelGroup(BaseModel):
    group_id: str
    panels: list[str] = Field(
        description="List of panel_ids in this group"
    )
    reading_direction: ReadingDirection = ReadingDirection.RTL
    is_continuous: bool = False


class ReadingOrder(BaseModel):
    page_id: str
    sequence: list[str] = Field(
        description="Ordered list of panel_ids"
    )
    groups: list[PanelGroup] = Field(default_factory=list)
    confidence: float = Field(
        description="Overall confidence in this ordering 0-1"
    )
    ambiguous_regions: list[list[str]] = Field(
        default_factory=list,
        description="Groups of panels where order is uncertain"
    )
    reasoning: list[str] = Field(
        default_factory=list,
        description="Human-readable explanations"
    )


class PageAnalysis(BaseModel):
    page_id: str
    width: int
    height: int
    panels: list[Panel]
    reading_order: Optional[ReadingOrder] = None
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class ChapterAnalysis(BaseModel):
    chapter_id: str
    pages: list[PageAnalysis]
    total_pages: int
    pages_needing_review: int = 0
