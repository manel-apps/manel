from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import click
from PIL import Image
from tqdm import tqdm

from manel.export_kindle.exporter import export_to_kindle
from manel.ingestion.ingest import ingest
from manel.models import ChapterAnalysis, PageAnalysis, Panel, PanelType
from manel.sequencing.sequencer import sequence_page
from manel.ui.editor import launch_review_ui
from manel.utils.preprocess import preprocess_for_analysis
from manel.validation.validator import validate_chapter, validate_page
from manel.vision.detector import VisionPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("manga_transformer")


class MangaTransformerPipeline:
    def __init__(
        self,
        device: Optional[str] = None,
        model_path: Optional[str | Path] = None,
    ):
        self.vision = VisionPipeline(device=device, model_path=model_path)

    def process_chapter(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        chapter_id: Optional[str] = None,
        review: bool = False,
        export: bool = True,
    ) -> ChapterAnalysis:
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Loading images from {input_path}")
        original_images = ingest(input_path)
        logger.info(f"Loaded {len(original_images)} page(s)")

        chapter_id = chapter_id or input_path.stem or f"chapter_{uuid.uuid4().hex[:8]}"

        pages = []
        for i, image in enumerate(tqdm(original_images, desc="Analyzing pages")):
            page_id = f"{chapter_id}_p{i+1:04d}"

            logger.info(f"Analyzing page {i+1}/{len(original_images)}")
            analysis = self.vision.analyze_page(image, page_id)

            if not analysis.panels:
                analysis.panels = [
                    Panel(
                        panel_id=f"{page_id}_p001",
                        bbox=(0.0, 0.0, 1.0, 1.0),
                        panel_type=PanelType.MAIN,
                        area_ratio=1.0,
                        has_text=False,
                        text_content=None,
                        visual_weight=0.5,
                        confidence=0.5,
                    )
                ]
                logger.info(f"  [FALLBACK] Using full-page panel for page {i+1}")

            logger.info(f"Sequencing page {i+1}")
            analysis.reading_order = sequence_page(analysis)

            logger.info(f"Validating page {i+1}")
            analysis, errors = validate_page(analysis)

            if errors:
                for error in errors:
                    logger.info(f"  {error}")

            pages.append(analysis)

        chapter_analysis = ChapterAnalysis(
            chapter_id=chapter_id,
            pages=pages,
            total_pages=len(pages),
        )

        validation_summary = validate_chapter(chapter_analysis)
        logger.info(f"\nValidation summary:")
        logger.info(f"  Total pages: {validation_summary['total_pages']}")
        logger.info(f"  Pages needing review: {validation_summary['pages_needing_review']}")
        logger.info(f"  Average confidence: {validation_summary['average_confidence']:.2f}")
        logger.info(f"  Quality score: {validation_summary['quality_score']}")

        metadata_path = output_dir / f"{chapter_id}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(chapter_analysis.model_dump(), f, indent=2, default=str)
        logger.info(f"Metadata saved to {metadata_path}")

        if review and validation_summary["pages_needing_review"] > 0:
            logger.info("Launching review UI...")
            launch_review_ui(chapter_analysis, original_images)

        if export:
            logger.info("Exporting to Kindle format...")
            epub_path = export_to_kindle(
                chapter_analysis,
                original_images,
                output_dir,
                chapter_id=chapter_id,
            )
            logger.info(f"Exported to {epub_path}")

        return chapter_analysis


@click.group()
def cli():
    """Manel - Manga Panel Reader"""
    pass


@cli.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_dir", type=click.Path())
@click.option("--chapter-id", default=None, help="Chapter identifier")
@click.option("--review", is_flag=True, help="Launch review UI after processing")
@click.option("--no-export", is_flag=True, help="Skip Kindle export")
@click.option("--device", default=None, help="Device to use (cuda/cpu)")
@click.option("--model-path", default=None, help="Path to custom model")
def process(
    input_path: str,
    output_dir: str,
    chapter_id: Optional[str],
    review: bool,
    no_export: bool,
    device: Optional[str],
    model_path: Optional[str],
):
    """Process a manga chapter or page"""
    pipeline = MangaTransformerPipeline(device=device, model_path=model_path)
    pipeline.process_chapter(
        input_path=input_path,
        output_dir=output_dir,
        chapter_id=chapter_id,
        review=review,
        export=not no_export,
    )


@cli.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--device", default=None, help="Device to use (cuda/cpu)")
def preview(input_path: str, device: Optional[str]):
    """Preview panel detection on a single page"""
    from manel.ingestion.ingest import ingest_single

    image = ingest_single(input_path)
    pipeline = VisionPipeline(device=device)
    analysis = pipeline.analyze_page(image, "preview")

    print(f"\nDetected {len(analysis.panels)} panels:")
    for i, panel in enumerate(analysis.panels):
        print(
            f"  Panel {i+1}: bbox={panel.bbox}, confidence={panel.confidence:.2f}, "
            f"type={panel.panel_type.value}, area={panel.area_ratio:.2%}"
        )


@cli.command()
def gui():
    """Launch the graphical user interface"""
    import flet as ft
    from manel.gui import main as gui_main

    ft.run(main=gui_main)


@cli.command()
@click.argument("input_paths", nargs=-1, type=click.Path(exists=True))
@click.argument("output_dir", type=click.Path())
@click.option("--review", is_flag=True, help="Launch review UI after processing")
@click.option("--no-export", is_flag=True, help="Skip Kindle export")
@click.option("--device", default=None, help="Device to use (cuda/cpu)")
@click.option("--model-path", default=None, help="Path to custom model")
def batch(
    input_paths: tuple[str, ...],
    output_dir: str,
    review: bool,
    no_export: bool,
    device: Optional[str],
    model_path: Optional[str],
):
    """Process multiple manga files/directories at once"""
    from manel.ingestion.ingest import ingest_batch

    if not input_paths:
        raise click.UsageError("At least one input path is required")

    pipeline = MangaTransformerPipeline(device=device, model_path=model_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_items = ingest_batch(list(input_paths))

    for i, (source_path, images) in enumerate(tqdm(batch_items, desc="Processing files")):
        chapter_id = source_path.stem or f"chapter_{i:04d}"
        logger.info(f"[{i+1}/{len(batch_items)}] Processing: {source_path.name}")

        pages = []
        for page_idx, image in enumerate(tqdm(images, desc=f"  {source_path.name}", leave=False)):
            page_id = f"{chapter_id}_p{page_idx+1:04d}"
            analysis = pipeline.vision.analyze_page(image, page_id)
            analysis.reading_order = sequence_page(analysis)
            analysis, errors = validate_page(analysis)
            pages.append(analysis)

        chapter_analysis = ChapterAnalysis(
            chapter_id=chapter_id,
            pages=pages,
            total_pages=len(pages),
        )

        if not no_export:
            chapter_output = output_dir / chapter_id
            export_to_kindle(chapter_analysis, images, chapter_output, chapter_id=chapter_id)
            logger.info(f"  Exported: {chapter_output}")

    logger.info(f"\nBatch complete: {len(batch_items)} file(s) processed")


def main():
    cli()


if __name__ == "__main__":
    main()
