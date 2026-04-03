from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterator

from PIL import Image

from manel.models import PageAnalysis

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
CBZ_EXTENSIONS = {".cbz"}
CBR_EXTENSIONS = {".cbr"}
COMIC_EXTENSIONS = CBZ_EXTENSIONS | CBR_EXTENSIONS


class IngestionError(Exception):
    pass


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _is_pdf(path: Path) -> bool:
    return path.suffix.lower() in PDF_EXTENSIONS


def _is_cbz(path: Path) -> bool:
    return path.suffix.lower() in CBZ_EXTENSIONS


def _is_cbr(path: Path) -> bool:
    return path.suffix.lower() in CBR_EXTENSIONS


def _is_comic(path: Path) -> bool:
    return path.suffix.lower() in COMIC_EXTENSIONS


def _sort_natural(items):
    import re

    def natural_key(item):
        name = Path(item).name if hasattr(item, "name") else Path(item).name
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", name)]

    return sorted(items, key=natural_key)


def _load_cbz(path: Path) -> list[Image.Image]:
    images = []
    with zipfile.ZipFile(path, "r") as zf:
        for name in _sort_natural([n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTENSIONS]):
            with zf.open(name) as f:
                img = Image.open(f).convert("RGB")
                img.metadata = {"source": str(path), "filename": Path(name).name}
                images.append(img)
    if not images:
        raise IngestionError(f"No images found in CBZ: {path}")
    return images


def _load_cbr(path: Path) -> list[Image.Image]:
    try:
        import rarfile
    except ImportError:
        raise IngestionError("rarfile is required for CBR support. Install with: pip install rarfile")

    import sys

    if sys.platform == "win32":
        _ensure_unrar_windows()

    images = []
    try:
        with rarfile.RarFile(path, "r") as rf:
            for name in _sort_natural([n for n in rf.namelist() if Path(n).suffix.lower() in IMAGE_EXTENSIONS]):
                with rf.open(name) as f:
                    img = Image.open(f).convert("RGB")
                    img.metadata = {"source": str(path), "filename": Path(name).name}
                    images.append(img)
    except rarfile.NeedFirstVolume:
        raise IngestionError(f"Multi-volume RAR not supported: {path}")
    except rarfile.Error as e:
        raise IngestionError(f"Failed to open CBR: {e}")

    if not images:
        raise IngestionError(f"No images found in CBR: {path}")
    return images


def _ensure_unrar_windows():
    import rarfile
    import os
    import subprocess

    local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local"))
    manel_dir = os.path.join(local_appdata, "Manel", "tools")
    unrar_path = os.path.join(manel_dir, "UnRAR.exe")
    os.makedirs(manel_dir, exist_ok=True)

    if os.path.exists(unrar_path):
        rarfile.UNRAR_TOOL = unrar_path
        try:
            result = subprocess.run([unrar_path, "-v"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return
        except Exception:
            pass
        try:
            os.remove(unrar_path)
        except Exception:
            pass

    common_paths = [
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    ]
    for cp in common_paths:
        if os.path.exists(cp):
            rarfile.UNRAR_TOOL = cp
            try:
                result = subprocess.run([cp, "-v"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return
            except Exception:
                pass

    import shutil

    found = shutil.which("UnRAR.exe")
    if found:
        rarfile.UNRAR_TOOL = found
        return

    unrar_path = os.path.join(manel_dir, "UnRAR.exe")
    if not os.path.exists(unrar_path):
        try:
            import tempfile
            import urllib.request

            url = "https://www.rarlab.com/rar/unrarw64.exe"
            with tempfile.TemporaryDirectory() as tmpdir:
                installer = os.path.join(tmpdir, "unrar_setup.exe")
                urllib.request.urlretrieve(url, installer)
                subprocess.run(
                    [installer, "/S", f"/D={manel_dir}"],
                    capture_output=True,
                    timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
        except Exception:
            pass

    if os.path.exists(unrar_path):
        rarfile.UNRAR_TOOL = unrar_path
        return

    raise IngestionError(
        "UnRAR not found. Please install WinRAR or download UnRAR.exe from "
        "https://www.rarlab.com/download.htm and place it in: " + manel_dir
    )


def _load_comic(path: Path) -> list[Image.Image]:
    if _is_cbz(path):
        return _load_cbz(path)
    elif _is_cbr(path):
        return _load_cbr(path)
    raise IngestionError(f"Unsupported comic format: {path.suffix}")


def _load_image(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    img.metadata = {"source": str(path), "filename": path.name}
    return img


def _load_pdf(path: Path) -> list[Image.Image]:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise IngestionError("pypdf is required for PDF support. Install with: pip install pypdf")

    reader = PdfReader(str(path))
    images = []

    try:
        from pdf2image import convert_from_path

        images = convert_from_path(str(path), dpi=300)
        for i, img in enumerate(images):
            img.metadata = {"source": str(path), "filename": f"{path.stem}_page_{i+1:04d}.png"}
    except ImportError:
        import io

        for page_num, page in enumerate(reader.pages):
            from PIL import Image as PILImage

            if "/XObject" not in page["/Resources"]:
                continue
            xobjects = page["/Resources"]["/XObject"].get_object()
            for obj_name in xobjects:
                obj = xobjects[obj_name]
                if obj["/Subtype"] == "/Image":
                    data = obj.get_data()
                    if data:
                        img = PILImage.open(io.BytesIO(data)).convert("RGB")
                        img.metadata = {"source": str(path), "filename": f"{path.stem}_page_{page_num+1:04d}.png"}
                        images.append(img)
                        break

    if not images:
        raise IngestionError(f"No images could be extracted from PDF: {path}")

    return images


def ingest_single(path: str | Path) -> Image.Image:
    path = Path(path)
    if not path.exists():
        raise IngestionError(f"Path does not exist: {path}")

    if _is_image(path):
        return _load_image(path)
    elif _is_pdf(path):
        pdf_images = _load_pdf(path)
        if len(pdf_images) == 1:
            return pdf_images[0]
        raise IngestionError(f"PDF contains {len(pdf_images)} pages. Use ingest_chapter() for multi-page documents.")
    elif _is_comic(path):
        comic_images = _load_comic(path)
        if len(comic_images) == 1:
            return comic_images[0]
        raise IngestionError(
            f"Comic contains {len(comic_images)} pages. Use ingest_chapter() for multi-page documents."
        )
    else:
        raise IngestionError(f"Unsupported file format: {path.suffix}")


def ingest_chapter(path: str | Path) -> list[Image.Image]:
    path = Path(path)
    if not path.exists():
        raise IngestionError(f"Path does not exist: {path}")

    if _is_image(path):
        return [_load_image(path)]
    elif _is_pdf(path):
        return _load_pdf(path)
    elif _is_comic(path):
        return _load_comic(path)
    elif path.is_dir():
        images = []
        for file_path in _sort_natural([p for p in path.iterdir() if p.is_file() and _is_image(p)]):
            images.append(_load_image(file_path))
        if not images:
            raise IngestionError(f"No images found in directory: {path}")
        return images
    else:
        raise IngestionError(f"Unsupported path type: {path}")


def ingest(path: str | Path) -> list[Image.Image]:
    path = Path(path)
    if path.is_file():
        if _is_pdf(path):
            return _load_pdf(path)
        elif _is_comic(path):
            return _load_comic(path)
        return [_load_image(path)]
    elif path.is_dir():
        return ingest_chapter(path)
    else:
        raise IngestionError(f"Invalid path: {path}")


def ingest_batch(paths: list[str | Path]) -> list[tuple[Path, list[Image.Image]]]:
    """Ingest multiple files/directories for batch processing.

    Returns list of (source_path, images) tuples.
    """
    results = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            raise IngestionError(f"Path does not exist: {p}")

        if p.is_file():
            if _is_pdf(p) or _is_comic(p):
                results.append((p, ingest(p)))
            elif _is_image(p):
                results.append((p, [_load_image(p)]))
        elif p.is_dir():
            for file_path in _sort_natural([fp for fp in p.iterdir() if fp.is_file()]):
                if _is_pdf(file_path) or _is_comic(file_path) or _is_image(file_path):
                    results.append((file_path, ingest(file_path)))

    return results
