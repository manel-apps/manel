from __future__ import annotations

import logging
import threading
from pathlib import Path

import flet as ft

logger = logging.getLogger(__name__)

LANG_FILE = Path(__file__).parent / ".lang_preference"

TRANSLATIONS = {
    "en": {
        "title": "Manel",
        "subtitle": "Manga Panel Transformer",
        "input_hint": "Drag & drop files here, or type paths (one per line)",
        "output_label": "Output Directory",
        "output_browse": "Browse",
        "device_label": "Device",
        "review_label": "Launch review UI after processing",
        "start_btn": "Start Processing",
        "status_label": "Status",
        "status_idle": "Idle",
        "status_running": "Processing...",
        "status_done": "Done!",
        "status_error": "Error",
        "lang_label": "Language",
        "log_title": "Log",
        "no_input": "Please add at least one input file",
        "no_output": "Please select an output directory",
        "done": "Batch complete: {count} file(s) processed",
        "error": "Error: {msg}",
        "cuda": "CUDA (GPU)",
        "cpu": "CPU",
        "file_list": "Files to process",
        "window_title": "Manel (Manga Panel Transformer)",
        "starting": "Starting batch processing...",
        "processing": "Processing: {name}",
        "exported": "Exported: {path}",
        "add_files": "Add Files",
        "clear": "Clear",
        "select_files": "Select comic files",
        "ocr_label": "Enable text detection (OCR)",
    },
    "es": {
        "title": "Manel",
        "subtitle": "Transformador de paneles de manga",
        "input_hint": "Arrastra archivos aqui, o escribe rutas (una por linea)",
        "output_label": "Directorio de salida",
        "output_browse": "Examinar",
        "device_label": "Dispositivo",
        "review_label": "Abrir UI de revision despues del procesamiento",
        "start_btn": "Iniciar Procesamiento",
        "status_label": "Estado",
        "status_idle": "En espera",
        "status_running": "Procesando...",
        "status_done": "Listo!",
        "status_error": "Error",
        "lang_label": "Idioma",
        "log_title": "Registro",
        "no_input": "Por favor agrega al menos un archivo",
        "no_output": "Por favor selecciona un directorio de salida",
        "done": "Lote completo: {count} archivo(s) procesado(s)",
        "error": "Error: {msg}",
        "cuda": "CUDA (GPU)",
        "cpu": "CPU",
        "file_list": "Archivos a procesar",
        "window_title": "Manel (Transformador de Paneles de Manga)",
        "starting": "Iniciando procesamiento por lotes...",
        "processing": "Procesando: {name}",
        "exported": "Exportado: {path}",
        "add_files": "Agregar Archivos",
        "clear": "Limpiar",
        "select_files": "Seleccionar archivos de comic",
        "ocr_label": "Activar deteccion de texto (OCR)",
    },
}


def _load_lang() -> str:
    if LANG_FILE.exists():
        return LANG_FILE.read_text().strip()
    return "en"


def _save_lang(lang: str) -> None:
    LANG_FILE.write_text(lang)


class MangaTransformerGUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.input_files: list[Path] = []

        self.lang = _load_lang()
        self.t = TRANSLATIONS[self.lang]

        page.title = self._t("window_title")
        page.window_width = 750
        page.window_height = 800
        page.window_resizable = True
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.padding = 20
        page.spacing = 10

        self.assets_dir = Path(__file__).parent / "assets"
        self._set_window_icon(page)

        page.window_bgcolor = None

        self.input_text = ft.TextField(
            label=self._t("file_list"),
            hint_text=self._t("input_hint"),
            multiline=True,
            min_lines=3,
            max_lines=6,
            read_only=True,
            expand=True,
        )
        self.output_field = ft.TextField(
            label=self._t("output_label"),
            expand=True,
        )
        self.device_radio = ft.RadioGroup(
            ft.Row(
                [
                    ft.Radio(value="cuda", label=self._t("cuda")),
                    ft.Radio(value="cpu", label=self._t("cpu")),
                ]
            ),
            value="cuda",
        )
        self.ocr_checkbox = ft.Checkbox(
            label=self._t("ocr_label"),
            value=False,
        )
        self.status_text = ft.Text(self._t("status_idle"), color=ft.Colors.ON_SURFACE_VARIANT)
        self.log_text = ft.Text("", size=12, font_family="monospace", selectable=True)

        self._build()

    def _set_window_icon(self, page):
        import sys

        if sys.platform != "win32":
            return

        icon_path = str(self.assets_dir / "app_icon_light.ico")
        if not Path(icon_path).exists():
            return

        import ctypes
        import ctypes.wintypes
        import time
        import threading

        WM_SETICON = 0x0080
        ICON_BIG = 1
        LR_LOADFROMFILE = 0x00000010
        LR_DEFAULTSIZE = 0x00000040

        def _apply_icon():
            time.sleep(1.5)
            try:
                icon = ctypes.windll.user32.LoadImageW(0, icon_path, 1, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                if not icon:
                    return

                def enum_cb(hwnd, _):
                    title_len = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if title_len > 0:
                        buf = ctypes.create_unicode_buffer(title_len + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, title_len + 1)
                        if "Manel" in buf.value:
                            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, icon)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            except Exception:
                pass

        threading.Thread(target=_apply_icon, daemon=True).start()

    def _t(self, key: str) -> str:
        return self.t.get(key, key)

    def _build(self):
        self.page.controls.clear()

        self.page.add(
            ft.Row(
                [
                    ft.Image(
                        src=str(self.assets_dir / "logo.png"),
                        width=48,
                        height=48,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    ft.Container(expand=True),
                    ft.Dropdown(
                        label=self._t("lang_label"),
                        value=self.lang,
                        options=[
                            ft.dropdown.Option("en", "English"),
                            ft.dropdown.Option("es", "Espanol"),
                        ],
                        width=140,
                        on_select=self._on_lang_change,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Text(self._t("subtitle"), size=14, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Divider(),
            ft.Row(
                [
                    ft.Text(self._t("file_list"), weight=ft.FontWeight.BOLD, size=14),
                    ft.Container(expand=True),
                    ft.TextButton(
                        self._t("clear"),
                        on_click=self._clear_files,
                    ),
                ]
            ),
            ft.Row(
                [
                    self.input_text,
                    ft.ElevatedButton(
                        self._t("add_files"),
                        icon=ft.Icons.ADD,
                        on_click=self._add_files,
                    ),
                ]
            ),
            ft.Row(
                [
                    self.output_field,
                    ft.ElevatedButton(
                        self._t("output_browse"),
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._browse_output,
                    ),
                ]
            ),
            ft.Column(
                [
                    ft.Text(self._t("device_label"), weight=ft.FontWeight.BOLD),
                    self.device_radio,
                ]
            ),
            self.ocr_checkbox,
            ft.Divider(),
            ft.Row(
                [
                    ft.ElevatedButton(
                        self._t("start_btn"),
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=self._start,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.PRIMARY,
                            color=ft.Colors.ON_PRIMARY,
                        ),
                    ),
                    ft.Container(expand=True),
                    ft.Text(self._t("status_label"), weight=ft.FontWeight.BOLD),
                    self.status_text,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Divider(),
            ft.Text(self._t("log_title"), weight=ft.FontWeight.BOLD, size=14),
            ft.Container(
                content=self.log_text,
                padding=10,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
                border_radius=8,
                expand=True,
            ),
        )

    def _on_lang_change(self, e):
        self.lang = e.control.value
        _save_lang(self.lang)
        self.t = TRANSLATIONS[self.lang]
        self._build()

    def _get_input_paths(self) -> list[Path]:
        return self.input_files[:]

    def _setup_tkinter_icon(self, root):
        ico_path = str(self.assets_dir / "app_icon_light.ico")
        if Path(ico_path).exists():
            try:
                root.iconbitmap(ico_path)
            except Exception:
                try:
                    import base64
                    import io
                    from PIL import Image as PILImage

                    img = PILImage.open(ico_path)
                    from tkinter import PhotoImage

                    img_data = io.BytesIO()
                    img.save(img_data, format="PNG")
                    b64 = base64.b64encode(img_data.getvalue()).decode()
                    icon = PhotoImage(data=b64)
                    root.tk.call("wm", "iconphoto", root._w, icon)
                except Exception:
                    pass

    def _add_files(self, e):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.overrideredirect(True)
        root.geometry("0x0+0+0")
        self._setup_tkinter_icon(root)
        result = filedialog.askopenfilenames(
            title=self._t("select_files"),
            filetypes=[
                ("Comic files", "*.pdf *.cbr *.cbz"),
                ("PDF", "*.pdf"),
                ("CBR", "*.cbr"),
                ("CBZ", "*.cbz"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        if result:
            for path in result:
                p = Path(path)
                if p not in self.input_files:
                    self.input_files.append(p)
            self._update_input_display()
            self.page.update()

    def _update_input_display(self):
        lines = [str(p) for p in self.input_files]
        self.input_text.value = "\n".join(lines)

    def _clear_files(self, e):
        self.input_files.clear()
        self.input_text.value = ""
        self.page.update()

    def _remove_file(self, path: Path):
        if path in self.input_files:
            self.input_files.remove(path)
            self._update_input_display()
            self.page.update()

    def _browse_output(self, e):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.overrideredirect(True)
        root.geometry("0x0+0+0")
        self._setup_tkinter_icon(root)
        result = filedialog.askdirectory()
        root.destroy()
        if result:
            self.output_field.value = result
            self.page.update()

    def _show_message(self, message):
        ico_path = str(self.assets_dir / "app_icon_light.ico")
        icon = None
        if Path(ico_path).exists():
            try:
                import base64
                import io
                from PIL import Image as PILImage

                img = PILImage.open(ico_path)
                img_data = io.BytesIO()
                img.save(img_data, format="PNG")
                b64 = base64.b64encode(img_data.getvalue()).decode()
                from tkinter import PhotoImage

                icon = PhotoImage(data=b64)
            except Exception:
                pass

        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        self._setup_tkinter_icon(root)
        messagebox.showinfo("Manel", message, parent=root)
        root.destroy()

    def _start(self, e):
        input_paths = self._get_input_paths()
        if not input_paths:
            self._show_message(self._t("no_input"))
            return
        if not self.output_field.value:
            self._show_message(self._t("no_output"))
            return

        device = self.device_radio.value if self.device_radio else "cuda"
        ocr = self.ocr_checkbox.value if self.ocr_checkbox else False

        self.status_text.value = self._t("status_running")
        self.status_text.color = ft.Colors.PRIMARY
        self.log_text.value = self._t("starting") + "\n"
        self.page.update()

        thread = threading.Thread(
            target=self._run_batch,
            args=(input_paths, self.output_field.value, device, ocr),
            daemon=True,
        )
        thread.start()

    def _run_batch(self, input_paths, output_path, device, ocr):
        try:
            from manel.cli import MangaTransformerPipeline
            from manel.export_kindle.exporter import export_to_kindle
            from manel.ingestion.ingest import ingest
            from manel.models import ChapterAnalysis
            from manel.sequencing.sequencer import sequence_page
            from manel.validation.validator import validate_page

            pipeline = MangaTransformerPipeline(device=device)
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)

            for i, src_str in enumerate(input_paths):
                src = Path(src_str)
                self.log_text.value += f"\n[{i+1}/{len(input_paths)}] {self._t('processing').format(name=src.name)}\n"
                self.page.update()

                images = ingest(src)
                chapter_id = src.stem or f"chapter_{i:04d}"

                pages = []
                for page_idx, image in enumerate(images):
                    page_id = f"{chapter_id}_p{page_idx+1:04d}"
                    analysis = pipeline.vision.analyze_page(image, page_id, use_ocr=ocr)
                    analysis.reading_order = sequence_page(analysis)
                    analysis, errors = validate_page(analysis)
                    pages.append(analysis)

                chapter_analysis = ChapterAnalysis(
                    chapter_id=chapter_id,
                    pages=pages,
                    total_pages=len(pages),
                )

                epub_path = export_to_kindle(chapter_analysis, images, output_dir, chapter_id=chapter_id)
                self.log_text.value += f"  {self._t('exported').format(path=epub_path)}\n"
                self.page.update()

            self.log_text.value += f"\n{self._t('done').format(count=len(input_paths))}"
            self.status_text.value = self._t("status_done")
            self.status_text.color = ft.Colors.GREEN
            self.page.update()

            self._show_message(self._t("done").format(count=len(input_paths)))
        except Exception as ex:
            self.log_text.value += f"\nError: {str(ex)}"
            self.status_text.value = self._t("status_error")
            self.status_text.color = ft.Colors.RED
            self.page.update()

            self._show_message(self._t("error").format(msg=str(ex)))


def main(page: ft.Page):
    MangaTransformerGUI(page)


if __name__ == "__main__":
    ft.app(target=main)
