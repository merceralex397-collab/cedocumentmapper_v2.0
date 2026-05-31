"""Document readers that convert source files into DocumentModel instances."""

from __future__ import annotations
from pathlib import Path

from .base import DocumentReader
from .pdf import PDFDocumentReader
from .docx import DocxDocumentReader
from .doc import DocDocumentReader
from .email import EmailDocumentReader
from .errors import ReaderError, UnsupportedFormatError

__all__ = [
    "DocumentReader",
    "PDFDocumentReader",
    "DocxDocumentReader",
    "DocDocumentReader",
    "EmailDocumentReader",
    "ReaderError",
    "UnsupportedFormatError",
    "get_reader_for_path",
]


def get_reader_for_path(path: Path) -> DocumentReader:
    """Return an appropriate DocumentReader instance for the given file path."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return PDFDocumentReader()
    elif suffix == ".docx":
        return DocxDocumentReader()
    elif suffix == ".doc":
        return DocDocumentReader()
    elif suffix in (".eml", ".msg"):
        return EmailDocumentReader()
    else:
        raise UnsupportedFormatError(f"Unsupported file format suffix: {suffix}")
