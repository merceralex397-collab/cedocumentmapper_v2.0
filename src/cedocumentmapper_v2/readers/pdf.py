from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path
import fitz
from pypdf import PdfReader
from PIL import Image as PILImage
import pytesseract

from cedocumentmapper_v2.domain.models import (
    DocumentModel,
    DocumentPage,
    DocumentLine,
)
from cedocumentmapper_v2.readers.base import DocumentReader
from cedocumentmapper_v2.readers.errors import ReaderError, DependencyMissingError

OCR_PAGE_LIMIT = 2


def resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / relative_path
    # Look next to the executing script/module
    curr = Path(__file__).resolve()
    # Travel up to find root of the repo (cedocumentmapper_v2.0)
    for parent in curr.parents:
        if (parent / "requirements.txt").exists():
            return parent / relative_path
    return curr.parent / relative_path


def configure_tesseract() -> bool:
    """Configure pytesseract using bundled binary if available."""
    try:
        tess_dir = resource_path("tesseract")
        if not tess_dir.exists():
            # Try parent directory / v1 directory as fallback
            tess_dir = Path("c:/Users/PC/Documents/GitHub/cedocumentmapper/tesseract")
        
        if not tess_dir.exists():
            return False

        candidates = [
            tess_dir / "tesseract.exe",
            tess_dir / "tesseract",
        ]
        binary = next((c for c in candidates if c.exists()), None)
        if binary is None:
            return False

        pytesseract.pytesseract.tesseract_cmd = str(binary)
        tessdata = tess_dir / "tessdata"
        if tessdata.exists():
            os.environ["TESSDATA_PREFIX"] = str(tessdata)
        return True
    except Exception:
        return False


class PDFDocumentReader(DocumentReader):
    supported_extensions: frozenset[str] = frozenset([".pdf"])

    def __init__(self) -> None:
        configure_tesseract()

    def read(self, path: Path) -> DocumentModel:
        if not path.exists():
            raise ReaderError(f"File not found: {path}")

        notes = []
        pages_list = []
        plain_text_parts = []

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            raise ReaderError(f"Could not open PDF with PyMuPDF: {exc}") from exc

        try:
            per_page_image_counts = []
            for page_idx, page in enumerate(doc):
                try:
                    per_page_image_counts.append(len(page.get_images() or []))
                except Exception:
                    per_page_image_counts.append(0)

                width = page.rect.width
                height = page.rect.height
                
                # Use dict mode to get styling and layout info
                text_dict = page.get_text("dict", sort=True)
                lines_list = []
                line_idx_counter = 0

                for block in text_dict.get("blocks", []):
                    if block.get("type") != 0:  # Skip image/non-text blocks
                        continue
                    
                    block_id = str(block.get("number", ""))
                    for line in block.get("lines", []):
                        bbox = line.get("bbox")  # (x0, y0, x1, y1)
                        line_text = ""
                        max_font_size = 0.0
                        is_bold = False
                        
                        spans = line.get("spans", [])
                        for span in spans:
                            span_text = span.get("text", "")
                            line_text += span_text
                            max_font_size = max(max_font_size, span.get("size", 0.0))
                            flags = span.get("flags", 0)
                            if flags & 16:  # bit 4 is bold
                                is_bold = True
                        
                        # Clean line text
                        line_text_cleaned = line_text.replace("\r", " ").replace("\t", " ").strip()
                        if line_text_cleaned:
                            lines_list.append(
                                DocumentLine(
                                    text=line_text_cleaned,
                                    page_index=page_idx,
                                    line_index=line_idx_counter,
                                    bbox=bbox,
                                    block_id=block_id,
                                    confidence=1.0,
                                )
                            )
                            line_idx_counter += 1

                # If PyMuPDF's dict mode returned no text, let's try get_text("text") as fallback
                if not lines_list:
                    fallback_text = page.get_text("text", sort=True) or ""
                    fallback_lines = [l.strip() for l in fallback_text.splitlines() if l.strip()]
                    for f_line in fallback_lines:
                        lines_list.append(
                            DocumentLine(
                                text=f_line,
                                page_index=page_idx,
                                line_index=line_idx_counter,
                                confidence=0.9,
                            )
                        )
                        line_idx_counter += 1

                pages_list.append(
                    DocumentPage(
                        page_index=page_idx,
                        width=width,
                        height=height,
                        lines=tuple(lines_list),
                    )
                )
                
                # Build page plain text
                page_text_combined = "\n".join(line.text for line in lines_list)
                plain_text_parts.append(page_text_combined)

            combined_text = "\n\n".join(plain_text_parts).strip()

            # OCR fallback checks
            should_ocr = (
                not combined_text
                and 0 < len(per_page_image_counts) <= OCR_PAGE_LIMIT
                and all(count == 1 for count in per_page_image_counts)
            )

            if should_ocr:
                notes.append("Selectable text empty. Initiating OCR fallback.")
                ocr_pages = []
                ocr_lines_list = []
                
                for page_idx, page in enumerate(doc):
                    try:
                        # Render page to high-res image
                        pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                        img_data = pix.tobytes("png")
                        img = PILImage.open(io.BytesIO(img_data))
                        
                        # Perform OCR
                        page_ocr = pytesseract.image_to_string(img, lang="eng") or ""
                        page_ocr_lines = [l.strip() for l in page_ocr.splitlines() if l.strip()]
                        
                        page_lines = []
                        for line_idx, line_text in enumerate(page_ocr_lines):
                            page_lines.append(
                                DocumentLine(
                                    text=line_text,
                                    page_index=page_idx,
                                    line_index=line_idx,
                                    confidence=0.7,
                                )
                            )
                        
                        ocr_lines_list.append(page_lines)
                        ocr_pages.append("\n".join(page_ocr_lines))
                    except Exception as ocr_exc:
                        notes.append(f"OCR failed on page {page_idx + 1}: {ocr_exc}")
                        break
                else:
                    # If all pages OCR'd successfully, override pages_list and combined_text
                    pages_list = []
                    for page_idx, p_lines in enumerate(ocr_lines_list):
                        pages_list.append(
                            DocumentPage(
                                page_index=page_idx,
                                width=doc[page_idx].rect.width,
                                height=doc[page_idx].rect.height,
                                lines=tuple(p_lines),
                            )
                        )
                    combined_text = "\n\n".join(ocr_pages).strip()
                    notes.append("Read PDF using OCR fallback.")

        finally:
            doc.close()

        # If PyMuPDF returned absolutely nothing (and we didn't do OCR), try pypdf fallback
        if not combined_text:
            try:
                reader = PdfReader(str(path))
                pypdf_pages = []
                pypdf_plain_text = []
                for page_idx, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    # Handle custom escape seq decoding
                    page_text = re.sub(r"/uni([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), page_text)
                    pypdf_page_lines = [l.strip() for l in page_text.splitlines() if l.strip()]
                    
                    lines_list = []
                    for line_idx, line_text in enumerate(pypdf_page_lines):
                        lines_list.append(
                            DocumentLine(
                                text=line_text,
                                page_index=page_idx,
                                line_index=line_idx,
                                confidence=0.8,
                            )
                        )
                    
                    pypdf_pages.append(
                        DocumentPage(
                            page_index=page_idx,
                            lines=tuple(lines_list),
                        )
                    )
                    pypdf_plain_text.append("\n".join(pypdf_page_lines))
                
                combined_text = "\n\n".join(pypdf_plain_text).strip()
                if combined_text:
                    pages_list = pypdf_pages
                    notes.append("Read PDF using pypdf fallback.")
            except Exception as pypdf_exc:
                notes.append(f"pypdf fallback failed: {pypdf_exc}")

        return DocumentModel(
            source_path=path,
            source_type="pdf",
            pages=tuple(pages_list),
            plain_text=combined_text,
            reader_notes=tuple(notes),
            metadata={
                "raw_text": combined_text,
                "raw_lines": combined_text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if combined_text else [],
                "page_count": len(pages_list),
                "ocr_page_limit": OCR_PAGE_LIMIT,
            },
        )
