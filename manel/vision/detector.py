from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO
from transformers import AutoModel, AutoImageProcessor

from manel.models import PageAnalysis, Panel, PanelType

logger = logging.getLogger(__name__)

PANEL_DETECTOR_MODEL = "mosesb/best-comic-panel-detection"
FEATURE_EXTRACTOR_MODEL = "facebook/dinov2-large"
KINDLE_WIDTH = 1072
KINDLE_HEIGHT = 1448


class PanelDetector:
    def __init__(
        self,
        device: Optional[str] = None,
        model_path: Optional[str | Path] = None,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading YOLOv12 panel detector on {self.device}")

        if model_path:
            self.model = YOLO(str(model_path))
        else:
            from huggingface_hub import hf_hub_download

            model_file = hf_hub_download(
                repo_id=PANEL_DETECTOR_MODEL,
                filename="best.pt",
            )
            self.model = YOLO(model_file)

        self.model.to(self.device)

    def detect_panels(self, image: Image.Image) -> list[dict]:
        w, h = image.size

        results = self.model(image, conf=0.15, iou=0.45, verbose=False)

        panels = []
        seen_regions = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                x_min, y_min, x_max, y_max = box.xyxy[0].cpu().numpy()
                confidence = float(box.conf[0].cpu().numpy())

                x_norm_min = x_min / w
                y_norm_min = y_min / h
                x_norm_max = x_max / w
                y_norm_max = y_max / h

                area_ratio = (x_norm_max - x_norm_min) * (y_norm_max - y_norm_min)

                if area_ratio < 0.005 or area_ratio > 0.95:
                    continue

                is_duplicate = False
                for seen in seen_regions:
                    iou = self._compute_iou((x_norm_min, y_norm_min, x_norm_max, y_norm_max), seen)
                    if iou > 0.7:
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue

                seen_regions.append((x_norm_min, y_norm_min, x_norm_max, y_norm_max))
                panels.append(
                    {
                        "bbox": (x_norm_min, y_norm_min, x_norm_max, y_norm_max),
                        "confidence": confidence,
                        "area_ratio": area_ratio,
                    }
                )

        return panels

    def _compute_iou(
        self,
        box1: tuple[float, float, float, float],
        box2: tuple[float, float, float, float],
    ) -> float:
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2

        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)

        if inter_x_max <= inter_x_min or inter_y_max <= inter_y_min:
            return 0.0

        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - inter_area

        return inter_area / union_area if union_area > 0 else 0.0


class VisualAnalyzer:
    def __init__(
        self,
        device: Optional[str] = None,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading DINOv2 feature extractor on {self.device}")

        self.processor = AutoImageProcessor.from_pretrained(FEATURE_EXTRACTOR_MODEL)
        self.model = AutoModel.from_pretrained(FEATURE_EXTRACTOR_MODEL)
        self.model.to(self.device)
        self.model.eval()

    def extract_features(self, image: Image.Image) -> np.ndarray:
        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        features = outputs.last_hidden_state.mean(dim=1)
        return features.cpu().numpy()

    def compute_visual_weight(self, image: Image.Image, panel_bbox: tuple[float, float, float, float]) -> float:
        x_min, y_min, x_max, y_max = panel_bbox
        w, h = image.size

        panel_img = image.crop(
            (
                int(x_min * w),
                int(y_min * h),
                int(x_max * w),
                int(y_max * h),
            )
        )

        features = self.extract_features(panel_img)
        contrast = np.std(features)

        area_ratio = (x_max - x_min) * (y_max - y_min)
        size_weight = min(area_ratio * 3, 1.0)

        return float(np.clip(0.6 * contrast + 0.4 * size_weight, 0, 1))

    def detect_inserts(self, panels: list[dict]) -> list[int]:
        insert_indices = []
        avg_area = np.mean([p["area_ratio"] for p in panels])

        for i, panel in enumerate(panels):
            if panel["area_ratio"] < avg_area * 0.3:
                insert_indices.append(i)

        return insert_indices


class TextDetector:
    def __init__(
        self,
        device: Optional[str] = None,
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading Surya OCR on {self.device}")

        try:
            from surya.detection import DetectionPredictor

            self.predictor = DetectionPredictor(device=self.device)
            self.available = True
        except ImportError:
            logger.warning("Surya not installed. Text detection will be disabled.")
            self.available = False

    def detect_text_in_panel(
        self, image: Image.Image, panel_bbox: tuple[float, float, float, float]
    ) -> tuple[bool, Optional[str]]:
        if not self.available:
            return False, None

        w, h = image.size
        panel_img = image.crop(
            (
                int(panel_bbox[0] * w),
                int(panel_bbox[1] * h),
                int(panel_bbox[2] * w),
                int(panel_bbox[3] * h),
            )
        )

        try:
            results = self.predictor([panel_img])
            has_text = len(results[0].bboxes) > 0
            return has_text, None
        except Exception as e:
            logger.warning(f"Text detection failed: {e}")
            return False, None


class VisionPipeline:
    def __init__(
        self,
        device: Optional[str] = None,
        model_path: Optional[str | Path] = None,
    ):
        self.panel_detector = PanelDetector(device=device, model_path=model_path)
        self.visual_analyzer = VisualAnalyzer(device=device)
        self.text_detector = TextDetector(device=device)

    def analyze_page(self, image: Image.Image, page_id: str, use_ocr: bool = False) -> PageAnalysis:
        w, h = image.size

        raw_panels = self.panel_detector.detect_panels(image)

        insert_indices = self.visual_analyzer.detect_inserts(raw_panels)

        panels = []
        for i, raw in enumerate(raw_panels):
            panel_type = PanelType.INSERT if i in insert_indices else PanelType.MAIN

            visual_weight = self.visual_analyzer.compute_visual_weight(image, raw["bbox"])

            if use_ocr:
                has_text, text_content = self.text_detector.detect_text_in_panel(image, raw["bbox"])
            else:
                has_text, text_content = False, None

            panel = Panel(
                panel_id=f"{page_id}_p{i+1:03d}",
                bbox=raw["bbox"],
                panel_type=panel_type,
                area_ratio=raw["area_ratio"],
                has_text=has_text,
                text_content=text_content,
                visual_weight=visual_weight,
                confidence=raw["confidence"],
            )
            panels.append(panel)

        analysis = PageAnalysis(
            page_id=page_id,
            width=w,
            height=h,
            panels=panels,
        )

        return analysis
