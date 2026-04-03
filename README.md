# Manel

![Manel Logo](manel/assets/logo.png)

Turn manga pages into panel-by-panel reading for Kindle.

Automatically detects panels, infers reading order, and exports optimized EPUB3 files.

## Features

- **Panel Detection with YOLOv12**: Specialized comic panel detection model trained on comic book pages
- **Visual Analysis with DINOv2**: Understands panel structure and relationships
- **OCR with Surya**: Optional text detection in panels (Japanese, disabled by default)
- **Manga Reading Order**: Automatic R→L, T→B inference with specialized heuristics
- **Confidence Handling**: Ambiguity detection with confidence levels
- **Multiple Input Formats**: PDF, CBR, CBZ, and image folders
- **Batch Processing**: Process multiple chapters at once via CLI or GUI
- **Kindle Export**: Single EPUB3 file optimized for Kindle 10th Gen (6", 1072×1448)
- **Bilingual GUI**: Desktop app in English/Spanish with language persistence and custom icons

## Tech Stack

| Component | Tool | Version |
|---|---|---|
| Panel Detection | YOLOv12x (mosesb/best-comic-panel-detection) | 2025 |
| Visual Features | DINOv2 (Meta) | 2024 |
| OCR | Surya | 2024-25 |
| ML Framework | PyTorch | 2.x |
| Desktop UI | Flet | 2025 |
| Review UI | Gradio | 5.x |
| Export | EPUB3 | - |
| Python | 3.12+ | - |

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

### Desktop GUI

Launch the graphical interface:

```bash
# Via installed command
manel gui

# Via launcher scripts (no install needed)
.\manel.bat gui    # Windows
./manel.sh gui     # Linux/Mac
```

The GUI supports English and Spanish, remembers your language preference, and provides:
- File selection via dialog (PDF, CBR, CBZ, images)
- Output directory selection
- Device selection (CUDA/CPU)
- Optional text detection (OCR) toggle, disabled by default
- Batch processing with progress log
- Custom Manel icons on all file dialogs

### CLI

Process a single chapter:

```bash
manel process /path/to/chapter /path/to/output --review
```

Process multiple files at once (batch):

```bash
manel batch chapter1.pdf chapter2.cbz chapter3.cbr /path/to/output
```

Options:

- `--chapter-id ID`: Chapter identifier
- `--review`: Launch correction UI after processing
- `--no-export`: Skip Kindle export
- `--device cuda/cpu`: Device to use
- `--model-path PATH`: Path to custom model

Preview panel detection on a single page:

```bash
manel preview /path/to/page.jpg
```

### Python API

```python
from manel import MangaTransformerPipeline

pipeline = MangaTransformerPipeline(device="cuda")

result = pipeline.process_chapter(
    input_path="manga/chapter_01/",
    output_dir="output/",
    chapter_id="my_manga_ch01",
    review=True,
    export=True,
)

print(f"Processed {result.total_pages} pages")
print(f"Pages needing review: {result.pages_needing_review}")
```

## Project Structure

```
manel/
├── ingestion/          # RF1: Image, PDF, CBR, CBZ ingestion
├── vision/             # RF2: Panel detection (YOLOv12 + DINOv2 + Surya)
├── sequencing/         # RF3: Manga reading order
├── validation/         # RF4: Confidence and ambiguity detection
├── export_kindle/      # RF7: EPUB3 export for Kindle
├── ui/                 # RF8: Assisted correction UI (Gradio)
├── models.py           # Data models (Panel, Page, ReadingOrder)
├── cli.py              # Main CLI
└── gui.py              # Flet desktop GUI
```

## Output Format

Single EPUB3 file with:

- Panel-by-panel navigation (each panel = one page)
- Images embedded in `OEBPS/images/` inside the EPUB
- Images optimized for 1072×1448 px
- NCX table of contents
- Reading order metadata

No intermediate folders or loose files are generated.

## System Requirements

- Python 3.12+
- GPU recommended (CUDA) for YOLOv12 and DINOv2
- ~4GB VRAM minimum for large models
- ~8GB RAM
- CBR support: UnRAR is auto-downloaded on Windows on first use, or install WinRAR / place `UnRAR.exe` in `%LOCALAPPDATA%\Manel\tools\`

## Acknowledgements

Manel builds on top of several open-source tools and models:

- **YOLOv12** (Ultralytics) for panel detection
- **DINOv2** (Meta) for visual feature extraction
- **Surya OCR** for optional text detection
- **PyTorch** for model execution
- **Flet** for the desktop GUI
- **Gradio** for the review interface

Special thanks to the open-source community for making these tools available.

## Disclaimer

This is an **experimental tool** that uses machine learning models for panel detection and reading order inference. Results may vary depending on the source material.

- Panel detection may miss or incorrectly identify panels, especially in complex layouts, double-page spreads, or heavily stylized pages
- Reading order inference is heuristic-based and may produce incorrect sequences in ambiguous cases
- OCR support is optional and disabled by default; when enabled, it may not work reliably with all text styles or languages
- Generated EPUB files may contain formatting inconsistencies

Always review the output before using it for final distribution. This tool is provided "as is" without warranty of any kind.

## License

MIT

