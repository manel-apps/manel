import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
import pytest

from manel.models import PageAnalysis, Panel, PanelType, ReadingOrder
from manel.sequencing.sequencer import sequence_page
from manel.validation.validator import validate_page, validate_chapter, ValidationError
from manel.export_kindle.exporter import export_to_kindle, _crop_and_resize
from manel.utils.preprocess import to_high_contrast_bw


@pytest.fixture
def sample_image():
    return Image.new("RGB", (800, 1200), color=(255, 255, 255))


@pytest.fixture
def sample_panel():
    return Panel(
        panel_id="test_p001",
        bbox=(0.1, 0.1, 0.9, 0.4),
        panel_type=PanelType.MAIN,
        area_ratio=0.24,
        has_text=True,
        text_content=None,
        visual_weight=0.7,
        confidence=0.9,
    )


@pytest.fixture
def sample_page(sample_panel):
    return PageAnalysis(
        page_id="test_page",
        width=800,
        height=1200,
        panels=[sample_panel],
        reading_order=ReadingOrder(
            page_id="test_page",
            sequence=["test_p001"],
            confidence=0.85,
        ),
    )


class TestModels:
    def test_panel_creation(self):
        panel = Panel(
            panel_id="p1",
            bbox=(0.0, 0.0, 1.0, 1.0),
            panel_type=PanelType.MAIN,
            area_ratio=1.0,
            has_text=False,
            text_content=None,
            visual_weight=0.5,
            confidence=0.8,
        )
        assert panel.panel_id == "p1"
        assert panel.panel_type == PanelType.MAIN
        assert panel.area_ratio == 1.0
        assert panel.confidence == 0.8

    def test_panel_type_values(self):
        assert PanelType.MAIN.value == "main"
        assert PanelType.INSERT.value == "insert"
        assert PanelType.DOUBLE_PAGE.value == "double_page"
        assert PanelType.ARTISTIC.value == "artistic"
        assert PanelType.UNKNOWN.value == "unknown"

    def test_page_analysis_creation(self):
        page = PageAnalysis(
            page_id="p1",
            width=1000,
            height=1500,
            panels=[],
        )
        assert page.page_id == "p1"
        assert page.width == 1000
        assert page.height == 1500
        assert page.needs_review is False

    def test_reading_order(self):
        order = ReadingOrder(
            page_id="test",
            sequence=["p1", "p2", "p3"],
            confidence=0.9,
        )
        assert len(order.sequence) == 3
        assert order.confidence == 0.9
        assert not order.ambiguous_regions


class TestValidation:
    def test_valid_page(self, sample_page):
        result, errors = validate_page(sample_page)
        assert not any(e.severity == "error" for e in errors)
        assert result.needs_review is False

    def test_no_panels(self):
        page = PageAnalysis(
            page_id="empty",
            width=800,
            height=1200,
            panels=[],
        )
        result, errors = validate_page(page)
        assert any(e.code == "NO_PANELS" for e in errors)
        assert result.needs_review is True

    def test_too_many_panels(self):
        panels = [
            Panel(
                panel_id=f"p{i}",
                bbox=(0.0, 0.0, 0.1, 0.1),
                panel_type=PanelType.MAIN,
                area_ratio=0.01,
                has_text=False,
                text_content=None,
                visual_weight=0.5,
                confidence=0.9,
            )
            for i in range(25)
        ]
        page = PageAnalysis(
            page_id="many",
            width=800,
            height=1200,
            panels=panels,
            reading_order=ReadingOrder(
                page_id="many",
                sequence=[p.panel_id for p in panels],
                confidence=0.9,
            ),
        )
        result, errors = validate_page(page)
        assert any(e.code == "TOO_MANY_PANELS" for e in errors)

    def test_low_confidence_reading_order(self):
        page = PageAnalysis(
            page_id="low_conf",
            width=800,
            height=1200,
            panels=[
                Panel(
                    panel_id="p1",
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    panel_type=PanelType.MAIN,
                    area_ratio=1.0,
                    has_text=False,
                    text_content=None,
                    visual_weight=0.5,
                    confidence=0.9,
                )
            ],
            reading_order=ReadingOrder(
                page_id="low_conf",
                sequence=["p1"],
                confidence=0.3,
            ),
        )
        result, errors = validate_page(page)
        assert any(e.code == "LOW_CONFIDENCE" for e in errors)
        assert result.needs_review is True

    def test_validate_chapter(self, sample_page):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        summary = validate_chapter(chapter)
        assert summary["total_pages"] == 1
        assert summary["pages_needing_review"] == 0


class TestSequencer:
    def test_single_panel_sequence(self, sample_page):
        order = sequence_page(sample_page)
        assert order is not None
        assert len(order.sequence) == 1
        assert order.sequence[0] == "test_p001"

    def test_no_panels_sequence(self):
        page = PageAnalysis(
            page_id="empty",
            width=800,
            height=1200,
            panels=[],
        )
        order = sequence_page(page)
        assert order is not None
        assert order.confidence == 0.0
        assert len(order.sequence) == 0


class TestCropAndResize:
    def test_crop_full_page(self, sample_image):
        result = _crop_and_resize(sample_image, (0.0, 0.0, 1.0, 1.0))
        assert result.size == (1072, 1448)
        assert result.mode == "RGB"

    def test_crop_centered(self, sample_image):
        result = _crop_and_resize(sample_image, (0.25, 0.25, 0.75, 0.75))
        assert result.size == (1072, 1448)
        assert result.mode == "RGB"

    def test_crop_preserves_content(self):
        img = Image.new("RGB", (800, 1200), color=(0, 0, 0))
        from PIL import ImageDraw

        draw = ImageDraw.Draw(img)
        draw.rectangle([200, 300, 600, 900], fill=(255, 255, 255))

        result = _crop_and_resize(img, (0.25, 0.25, 0.75, 0.75))
        assert result.size == (1072, 1448)


class TestPreprocess:
    def test_high_contrast_bw(self):
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        result = to_high_contrast_bw(img)
        assert result.mode == "L"
        assert result.size == (100, 100)

    def test_white_becomes_white(self):
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        result = to_high_contrast_bw(img)
        pixels = list(result.getdata())
        assert all(p == 255 for p in pixels)

    def test_black_becomes_black(self):
        img = Image.new("RGB", (100, 100), color=(0, 0, 0))
        result = to_high_contrast_bw(img)
        pixels = list(result.getdata())
        assert all(p == 0 for p in pixels)


class TestExport:
    @pytest.fixture
    def tmp_output(self, tmp_path):
        return tmp_path

    def test_export_creates_epub(self, sample_page, sample_image, tmp_output):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        epub_path = export_to_kindle(chapter, [sample_image], tmp_output, chapter_id="test")
        assert epub_path.exists()
        assert epub_path.suffix == ".epub"

    def test_export_epub_is_valid_zip(self, sample_page, sample_image, tmp_output):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        epub_path = export_to_kindle(chapter, [sample_image], tmp_output, chapter_id="test")
        assert zipfile.is_zipfile(epub_path)

    def test_export_contains_required_files(self, sample_page, sample_image, tmp_output):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        epub_path = export_to_kindle(chapter, [sample_image], tmp_output, chapter_id="test")

        with zipfile.ZipFile(epub_path) as zf:
            names = zf.namelist()
            assert "mimetype" in names
            assert "META-INF/container.xml" in names
            assert "OEBPS/content.opf" in names
            assert "OEBPS/toc.ncx" in names

    def test_export_images_in_oebps_images(self, sample_page, sample_image, tmp_output):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        epub_path = export_to_kindle(chapter, [sample_image], tmp_output, chapter_id="test")

        with zipfile.ZipFile(epub_path) as zf:
            names = zf.namelist()
            img_files = [n for n in names if n.endswith(".jpg")]
            assert len(img_files) > 0
            assert all("OEBPS/images/" in f for f in img_files)

    def test_export_xhtml_matches_panels(self, sample_page, sample_image, tmp_output):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        epub_path = export_to_kindle(chapter, [sample_image], tmp_output, chapter_id="test")

        with zipfile.ZipFile(epub_path) as zf:
            xhtml_files = [n for n in zf.namelist() if n.endswith(".xhtml")]
            assert len(xhtml_files) == 1

    def test_export_no_navbar_in_xhtml(self, sample_page, sample_image, tmp_output):
        from manel.models import ChapterAnalysis

        chapter = ChapterAnalysis(
            chapter_id="test",
            pages=[sample_page],
            total_pages=1,
        )
        epub_path = export_to_kindle(chapter, [sample_image], tmp_output, chapter_id="test")

        with zipfile.ZipFile(epub_path) as zf:
            xhtml_files = [n for n in zf.namelist() if n.endswith(".xhtml")]
            for xf in xhtml_files:
                content = zf.read(xf).decode("utf-8")
                assert "navbar" not in content.lower()


class TestGUI:
    def test_translations_exist(self):
        from manel.gui import TRANSLATIONS

        assert "en" in TRANSLATIONS
        assert "es" in TRANSLATIONS

    def test_translation_keys_match(self):
        from manel.gui import TRANSLATIONS

        en_keys = set(TRANSLATIONS["en"].keys())
        es_keys = set(TRANSLATIONS["es"].keys())
        assert en_keys == es_keys, f"Missing keys: EN only: {en_keys - es_keys}, ES only: {es_keys - en_keys}"

    def test_required_translation_keys(self):
        from manel.gui import TRANSLATIONS

        required_keys = {
            "title",
            "subtitle",
            "file_list",
            "output_label",
            "output_browse",
            "device_label",
            "start_btn",
            "status_label",
            "status_idle",
            "status_running",
            "status_done",
            "status_error",
            "lang_label",
            "log_title",
            "no_input",
            "no_output",
            "done",
            "error",
            "cuda",
            "cpu",
            "add_files",
            "clear",
            "select_files",
            "window_title",
            "starting",
            "processing",
            "exported",
        }
        for lang in ["en", "es"]:
            keys = set(TRANSLATIONS[lang].keys())
            missing = required_keys - keys
            assert not missing, f"Missing keys in {lang}: {missing}"

    def test_gui_has_no_review_checkbox(self):
        from manel.gui import MangaTransformerGUI
        import inspect

        source = inspect.getsource(MangaTransformerGUI)
        assert "review_checkbox" not in source, "review_checkbox is referenced but not defined"

    def test_gui_init_attributes(self):
        from manel.gui import MangaTransformerGUI
        import inspect

        source = inspect.getsource(MangaTransformerGUI.__init__)
        assert "self.page" in source
        assert "self.input_files" in source
        assert "self.input_text" in source
        assert "self.output_field" in source
        assert "self.device_radio" in source
        assert "self.ocr_checkbox" in source
        assert "self.status_text" in source
        assert "self.log_text" in source
        assert "self.assets_dir" in source

    def test_gui_build_references(self):
        from manel.gui import MangaTransformerGUI
        import inspect

        source = inspect.getsource(MangaTransformerGUI._build)
        assert "self.input_text" in source
        assert "self.output_field" in source
        assert "self.device_radio" in source
        assert "self.ocr_checkbox" in source
        assert "self.status_text" in source
        assert "self.log_text" in source
        assert "self.assets_dir" in source
        assert "review_checkbox" not in source

    def test_gui_start_references(self):
        from manel.gui import MangaTransformerGUI
        import inspect

        source = inspect.getsource(MangaTransformerGUI._start)
        assert "_get_input_paths" in source
        assert "self.output_field" in source
        assert "self.device_radio" in source
        assert "self.status_text" in source
        assert "self.log_text" in source
        assert "review_checkbox" not in source

    def test_gui_run_batch_references(self):
        from manel.gui import MangaTransformerGUI
        import inspect

        source = inspect.getsource(MangaTransformerGUI._run_batch)
        assert "self.log_text" in source
        assert "self.status_text" in source
        assert "self.page" in source
        assert "review_checkbox" not in source

    def test_lang_file_functions(self):
        from manel.gui import _load_lang, _save_lang, LANG_FILE
        import tempfile
        import os

        original = LANG_FILE
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            tmp_path = Path(f.name)

        try:
            import manel.gui as gui_module

            gui_module.LANG_FILE = tmp_path

            _save_lang("es")
            assert _load_lang() == "es"

            _save_lang("en")
            assert _load_lang() == "en"
        finally:
            gui_module.LANG_FILE = original
            if tmp_path.exists():
                tmp_path.unlink()
