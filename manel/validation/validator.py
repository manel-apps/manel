from __future__ import annotations

import logging

from manel.models import PageAnalysis, ReadingOrder

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD_HIGH = 0.8
CONFIDENCE_THRESHOLD_MEDIUM = 0.5
MAX_PANELS_PER_PAGE = 20
MIN_PANELS_PER_PAGE = 1


class ValidationError:
    def __init__(self, code: str, message: str, severity: str = "warning"):
        self.code = code
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.code}: {self.message}"


def validate_page(analysis: PageAnalysis) -> tuple[PageAnalysis, list[ValidationError]]:
    errors = []

    if not analysis.panels:
        errors.append(ValidationError(
            "NO_PANELS",
            "No panels detected on this page",
            severity="error"
        ))
        analysis.needs_review = True
        analysis.review_reasons.append("No panels detected")
        return analysis, errors

    if len(analysis.panels) > MAX_PANELS_PER_PAGE:
        errors.append(ValidationError(
            "TOO_MANY_PANELS",
            f"Detected {len(analysis.panels)} panels (max recommended: {MAX_PANELS_PER_PAGE})",
            severity="warning"
        ))

    if len(analysis.panels) < MIN_PANELS_PER_PAGE:
        errors.append(ValidationError(
            "TOO_FEW_PANELS",
            f"Only {len(analysis.panels)} panel(s) detected",
            severity="warning"
        ))

    if analysis.reading_order:
        confidence = analysis.reading_order.confidence

        if confidence < CONFIDENCE_THRESHOLD_MEDIUM:
            errors.append(ValidationError(
                "LOW_CONFIDENCE",
                f"Reading order confidence is {confidence:.2f} (threshold: {CONFIDENCE_THRESHOLD_MEDIUM})",
                severity="error"
            ))
            analysis.needs_review = True
            analysis.review_reasons.append(f"Low confidence: {confidence:.2f}")
        elif confidence < CONFIDENCE_THRESHOLD_HIGH:
            errors.append(ValidationError(
                "MEDIUM_CONFIDENCE",
                f"Reading order confidence is {confidence:.2f}",
                severity="warning"
            ))

        if analysis.reading_order.ambiguous_regions:
            n_ambiguous = len(analysis.reading_order.ambiguous_regions)
            errors.append(ValidationError(
                "AMBIGUOUS_REGIONS",
                f"{n_ambiguous} ambiguous region(s) in reading order",
                severity="warning"
            ))
            analysis.needs_review = True
            analysis.review_reasons.append(f"{n_ambiguous} ambiguous region(s)")

    low_confidence_panels = [p for p in analysis.panels if p.confidence < 0.5]
    if low_confidence_panels:
        errors.append(ValidationError(
            "LOW_CONFIDENCE_PANELS",
            f"{len(low_confidence_panels)} panel(s) with low detection confidence",
            severity="warning"
        ))

    return analysis, errors


def validate_chapter(chapter_analysis) -> dict:
    pages_needing_review = []
    total_confidence = 0
    n_pages = len(chapter_analysis.pages)

    for page in chapter_analysis.pages:
        if page.needs_review:
            pages_needing_review.append({
                "page_id": page.page_id,
                "reasons": page.review_reasons,
            })

        if page.reading_order:
            total_confidence += page.reading_order.confidence

    avg_confidence = total_confidence / n_pages if n_pages > 0 else 0

    chapter_analysis.pages_needing_review = len(pages_needing_review)

    return {
        "total_pages": n_pages,
        "pages_needing_review": len(pages_needing_review),
        "review_pages": pages_needing_review,
        "average_confidence": avg_confidence,
        "quality_score": "good" if avg_confidence >= CONFIDENCE_THRESHOLD_HIGH
            else "acceptable" if avg_confidence >= CONFIDENCE_THRESHOLD_MEDIUM
            else "poor",
    }
