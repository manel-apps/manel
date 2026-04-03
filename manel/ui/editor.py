from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import gradio as gr
from PIL import Image as PILImage

from manel.models import ChapterAnalysis, PageAnalysis, ReadingOrder
from manel.sequencing.sequencer import sequence_page
from manel.validation.validator import validate_page

logger = logging.getLogger(__name__)


class ReviewUI:
    def __init__(self, chapter_analysis: ChapterAnalysis, images: list[PILImage.Image]):
        self.chapter = chapter_analysis
        self.images = images
        self.current_page = 0

    def get_page_display(self, page_idx: int):
        if page_idx < 0 or page_idx >= len(self.images):
            return None, "Página inválida", None, None

        page = self.chapter.pages[page_idx]
        image = self.images[page_idx]

        display_img = self._draw_panel_overlay(image, page)

        info = self._build_page_info(page, page_idx)

        order_choices = self._build_order_choices(page)

        return display_img, info, order_choices, page_idx

    def _draw_panel_overlay(
        self, image: PILImage.Image, page: PageAnalysis
    ) -> PILImage.Image:
        import numpy as np

        img_copy = image.copy()
        w, h = img_copy.size

        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img_copy)

            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            except:
                font = ImageFont.load_default()

            for i, panel in enumerate(page.panels):
                x_min = int(panel.bbox[0] * w)
                y_min = int(panel.bbox[1] * h)
                x_max = int(panel.bbox[2] * w)
                y_max = int(panel.bbox[3] * h)

                color = "red" if panel.confidence < 0.5 else "lime"
                draw.rectangle([x_min, y_min, x_max, y_max], outline=color, width=3)

                label = f"P{i+1}"
                bbox = draw.textbbox((x_min, y_min), label, font=font)
                draw.rectangle(bbox, fill="black")
                draw.text((x_min, y_min), label, fill="white", font=font)

        except ImportError:
            logger.warning("PIL drawing not available, showing original image")

        return img_copy

    def _build_page_info(self, page: PageAnalysis, page_idx: int) -> str:
        info = f"**Página {page_idx + 1}/{len(self.images)}**\n\n"
        info += f"- Paneles detectados: {len(page.panels)}\n"

        if page.reading_order:
            info += f"- Confianza del orden: {page.reading_order.confidence:.2f}\n"
            info += f"- Secuencia: {', '.join(page.reading_order.sequence)}\n"
            if page.reading_order.reasoning:
                info += "\n**Razonamiento:**\n"
                for reason in page.reading_order.reasoning:
                    info += f"- {reason}\n"
        else:
            info += "- Sin orden de lectura generado\n"

        if page.needs_review:
            info += "\n⚠️ **Requiere revisión:**\n"
            for reason in page.review_reasons:
                info += f"- {reason}\n"

        return info

    def _build_order_choices(self, page: PageAnalysis) -> list:
        if not page.reading_order:
            return []

        choices = []
        for i, panel_id in enumerate(page.reading_order.sequence):
            panel = next((p for p in page.panels if p.panel_id == panel_id), None)
            if panel:
                choices.append(gr.Dropdown(
                    label=f"Posición {i+1}",
                    value=panel_id,
                    choices=[p.panel_id for p in page.panels],
                ))
        return choices

    def reorder_panels(self, page_idx: int, new_order: list[str]) -> tuple:
        page = self.chapter.pages[page_idx]
        if not page.reading_order:
            return self.get_page_display(page_idx)

        page.reading_order.sequence = new_order
        page.reading_order.confidence = 1.0
        page.needs_review = False
        page.review_reasons = []

        return self.get_page_display(page_idx)

    def exclude_panel(self, page_idx: int, panel_id: str) -> tuple:
        page = self.chapter.pages[page_idx]
        page.panels = [p for p in page.panels if p.panel_id != panel_id]

        if page.reading_order:
            page.reading_order.sequence = [
                pid for pid in page.reading_order.sequence if pid != panel_id
            ]

        return self.get_page_display(page_idx)

    def prev_page(self, page_idx: int) -> tuple:
        new_idx = max(0, page_idx - 1)
        self.current_page = new_idx
        return self.get_page_display(new_idx)

    def next_page(self, page_idx: int) -> tuple:
        new_idx = min(len(self.images) - 1, page_idx + 1)
        self.current_page = new_idx
        return self.get_page_display(new_idx)

    def launch(self, server_port: int = 7860):
        with gr.Blocks(title="Manga Transformer - Revisión") as app:
            gr.Markdown("# Manga Transformer - Revisión de Paneles")
            gr.Markdown("Revisa y corrige el orden de lectura detectado antes de exportar")

            current_page_state = gr.State(value=0)

            with gr.Row():
                prev_btn = gr.Button("← Anterior")
                next_btn = gr.Button("Siguiente →")

            page_display = gr.Image(label="Página con paneles detectados")
            page_info = gr.Markdown()
            order_dropdown = gr.Dropdown(
                label="Orden de lectura",
                choices=[],
                multiselect=True,
            )

            with gr.Row():
                exclude_btn = gr.Button("Excluir panel seleccionado", variant="stop")
                approve_btn = gr.Button("Aprobar página", variant="primary")

            exclude_panel_id = gr.Dropdown(label="Panel a excluir", choices=[])

            def update_page(page_idx):
                return self.get_page_display(page_idx)

            def on_prev(page_idx):
                new_idx = max(0, page_idx - 1)
                self.current_page = new_idx
                return (*self.get_page_display(new_idx), new_idx)

            def on_next(page_idx):
                new_idx = min(len(self.images) - 1, page_idx + 1)
                self.current_page = new_idx
                return (*self.get_page_display(new_idx), new_idx)

            prev_btn.click(
                on_prev,
                inputs=[current_page_state],
                outputs=[page_display, page_info, order_dropdown, current_page_state]
            )
            next_btn.click(
                on_next,
                inputs=[current_page_state],
                outputs=[page_display, page_info, order_dropdown, current_page_state]
            )

            app.load(
                update_page,
                inputs=[current_page_state],
                outputs=[page_display, page_info, order_dropdown]
            )

        app.launch(server_port=server_port, share=False)


def launch_review_ui(
    chapter_analysis: ChapterAnalysis,
    images: list[PILImage.Image],
    server_port: int = 7860,
):
    ui = ReviewUI(chapter_analysis, images)
    ui.launch(server_port=server_port)
