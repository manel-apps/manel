from __future__ import annotations

import io
import logging
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from PIL import Image

from manel.models import ChapterAnalysis, PageAnalysis

logger = logging.getLogger(__name__)

KINDLE_WIDTH = 1072
KINDLE_HEIGHT = 1448


def _crop_and_resize(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    target_width: int = KINDLE_WIDTH,
    target_height: int = KINDLE_HEIGHT,
) -> Image.Image:
    w, h = image.size
    x_min = int(bbox[0] * w)
    y_min = int(bbox[1] * h)
    x_max = int(bbox[2] * w)
    y_max = int(bbox[3] * h)

    x_min = max(0, min(x_min, w))
    y_min = max(0, min(y_min, h))
    x_max = max(x_min + 1, min(x_max, w))
    y_max = max(y_min + 1, min(y_max, h))

    panel = image.crop((x_min, y_min, x_max, y_max))

    panel_ratio = panel.width / panel.height
    target_ratio = target_width / target_height

    if panel_ratio > target_ratio:
        new_width = target_width
        new_height = int(target_width / panel_ratio)
    else:
        new_height = target_height
        new_width = int(target_height * panel_ratio)

    panel = panel.resize((new_width, new_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (target_width, target_height), (255, 255, 255))
    paste_x = (target_width - new_width) // 2
    paste_y = (target_height - new_height) // 2
    canvas.paste(panel.convert("RGB"), (paste_x, paste_y))

    return canvas


def _generate_ncx(chapter_id: str, chapter_analysis: ChapterAnalysis) -> str:
    nav_points = []
    play_order = 0

    for page_idx, page in enumerate(chapter_analysis.pages):
        if not page.reading_order:
            continue

        for seq_idx, panel_id in enumerate(page.reading_order.sequence):
            play_order += 1
            src = f"panel_{page_idx+1:04d}_{seq_idx+1:03d}.xhtml"
            nav_points.append(
                f'    <navPoint id="{panel_id}" playOrder="{play_order}">\n'
                f"      <navLabel><text>P{page_idx+1:02d}-{seq_idx+1:02d}</text></navLabel>\n"
                f'      <content src="{src}"/>\n'
                f"    </navPoint>"
            )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{uuid.uuid4()}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{chapter_id}</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>"""


def _generate_panel_xhtml(
    panel_img: Image.Image,
    filename: str,
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{filename}</title>
  <style>
    body {{ margin: 0; padding: 0; background: #000; }}
    .panel {{ text-align: center; margin: 0; padding: 0; width: 100%; height: 100%; }}
    .panel img {{ max-width: 100%; max-height: 100%; display: block; margin: 0 auto; }}
  </style>
</head>
<body>
  <div class="panel">
    <img src="images/{filename}" alt="Panel"/>
  </div>
</body>
</html>"""


def _generate_opf(
    chapter_id: str,
    chapter_analysis: ChapterAnalysis,
) -> str:
    manifest_items = [
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
    ]
    spine_items = []

    for page_idx, page in enumerate(chapter_analysis.pages):
        if page.reading_order:
            for seq_idx in range(len(page.reading_order.sequence)):
                panel_id = f"panel_{page_idx+1:04d}_{seq_idx+1:03d}"
                img_filename = f"{panel_id}.jpg"
                xhtml_filename = f"{panel_id}.xhtml"
                manifest_items.append(
                    f'    <item id="{panel_id}" href="{xhtml_filename}" media-type="application/xhtml+xml"/>'
                )
                manifest_items.append(
                    f'    <item id="img_{panel_id}" href="images/{img_filename}" media-type="image/jpeg"/>'
                )
                spine_items.append(f'    <itemref idref="{panel_id}"/>')
        else:
            full_id = f"page_{page_idx+1:04d}_full"
            img_filename = f"{full_id}.jpg"
            xhtml_filename = f"{full_id}.xhtml"
            manifest_items.append(
                f'    <item id="{full_id}" href="{xhtml_filename}" media-type="application/xhtml+xml"/>'
            )
            manifest_items.append(
                f'    <item id="img_{full_id}" href="images/{img_filename}" media-type="image/jpeg"/>'
            )
            spine_items.append(f'    <itemref idref="{full_id}"/>')

    manifest = "\n".join(manifest_items)
    spine = "\n".join(spine_items)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="uid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:{uuid.uuid4()}</dc:identifier>
    <dc:title>{chapter_id}</dc:title>
    <dc:language>ja</dc:language>
    <meta property="dcterms:modified">2026-04-01T00:00:00Z</meta>
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>"""


def _generate_container_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def export_to_kindle(
    chapter_analysis: ChapterAnalysis,
    images: list[Image.Image],
    output_path: str | Path,
    chapter_id: Optional[str] = None,
) -> Path:
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    chapter_id = chapter_id or f"manga_{uuid.uuid4().hex[:8]}"
    epub_path = output_path / f"{chapter_id}.epub"

    with zipfile.ZipFile(epub_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _generate_container_xml())
        zf.writestr("OEBPS/toc.ncx", _generate_ncx(chapter_id, chapter_analysis))
        zf.writestr("OEBPS/content.opf", _generate_opf(chapter_id, chapter_analysis))

        for page_idx, (page, image) in enumerate(zip(chapter_analysis.pages, images)):
            if page.reading_order:
                for seq_idx, panel_id in enumerate(page.reading_order.sequence):
                    panel = next((p for p in page.panels if p.panel_id == panel_id), None)
                    if not panel:
                        continue

                    panel_img = _crop_and_resize(image, panel.bbox)
                    img_filename = f"panel_{page_idx+1:04d}_{seq_idx+1:03d}.jpg"
                    xhtml_filename = f"panel_{page_idx+1:04d}_{seq_idx+1:03d}.xhtml"

                    img_buffer = io.BytesIO()
                    panel_img.save(img_buffer, "JPEG", quality=85, optimize=True)
                    zf.writestr(f"OEBPS/images/{img_filename}", img_buffer.getvalue())

                    xhtml_content = _generate_panel_xhtml(panel_img, img_filename)
                    zf.writestr(f"OEBPS/{xhtml_filename}", xhtml_content)
            else:
                full_img = _crop_and_resize(image, (0, 0, 1, 1))
                full_id = f"page_{page_idx+1:04d}_full"
                img_filename = f"{full_id}.jpg"
                xhtml_filename = f"{full_id}.xhtml"

                img_buffer = io.BytesIO()
                full_img.save(img_buffer, "JPEG", quality=85, optimize=True)
                zf.writestr(f"OEBPS/images/{img_filename}", img_buffer.getvalue())

                xhtml_content = _generate_panel_xhtml(full_img, img_filename)
                zf.writestr(f"OEBPS/{xhtml_filename}", xhtml_content)

    logger.info(f"Exported EPUB to {epub_path}")

    return epub_path
