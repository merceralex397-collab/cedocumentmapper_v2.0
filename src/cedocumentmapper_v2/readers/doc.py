from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from cedocumentmapper_v2.domain.models import (
    DocumentModel,
    DocumentPage,
    DocumentLine,
)
from cedocumentmapper_v2.readers.base import DocumentReader
from cedocumentmapper_v2.readers.errors import ReaderError, DependencyMissingError
from cedocumentmapper_v2.readers.docx import DocxDocumentReader


class DocDocumentReader(DocumentReader):
    supported_extensions: frozenset[str] = frozenset([".doc"])

    def read(self, path: Path) -> DocumentModel:
        if not path.exists():
            raise ReaderError(f"File not found: {path}")

        notes = []
        
        # Method 1: Try Microsoft Word COM Automation
        try:
            text = self._read_via_word_com(path)
            notes.append("Read DOC using Microsoft Word automation.")
            return self._build_model_from_text(path, text, notes)
        except Exception as com_exc:
            notes.append(f"Word COM extraction failed: {com_exc}")

        # Method 2: Try LibreOffice head-less docx conversion
        try:
            text = self._read_via_libreoffice(path)
            notes.append("Read DOC using LibreOffice conversion.")
            return self._build_model_from_text(path, text, notes)
        except Exception as lo_exc:
            notes.append(f"LibreOffice conversion failed: {lo_exc}")

        # Method 3: Try antiword text extraction for old binary DOC files.
        try:
            text = self._read_via_antiword(path)
            notes.append("Read DOC using antiword fallback.")
            return self._build_model_from_text(path, text, notes)
        except Exception as antiword_exc:
            notes.append(f"antiword extraction failed: {antiword_exc}")

        # Method 4: Some legacy DOC files in the corpus contain readable text
        # streams even when conversion tools are unavailable.
        try:
            text = self._read_via_binary_text_scrape(path)
            notes.append("Read DOC using embedded text scrape fallback.")
            return self._build_model_from_text(path, text, notes)
        except Exception as scrape_exc:
            notes.append(f"Embedded text scrape failed: {scrape_exc}")

        raise ReaderError(
            "Could not read DOC. Microsoft Word, LibreOffice, or antiword is required to extract text from legacy .doc files."
        )

    def _read_via_word_com(self, path: Path) -> str:
        try:
            import pythoncom
            from win32com.client import DispatchEx
        except ImportError as exc:
            raise DependencyMissingError("pywin32 / pythoncom is not installed.") from exc

        def clean_line_win32(text: str) -> str:
            text = (text or "").replace("\r\x07", "\n").replace("\x07", "")
            text = text.replace("\r", "\n")
            return text

        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            doc = word.Documents.Open(
                str(path.resolve()),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                Visible=False,
            )

            header_lines = []
            footer_lines = []
            seen_header = set()
            seen_footer = set()

            for section_index in range(1, doc.Sections.Count + 1):
                section = doc.Sections(section_index)
                for hf_type in (1, 2, 3):
                    try:
                        header_text = section.Headers(hf_type).Range.Text or ""
                    except Exception:
                        header_text = ""
                    header_text = clean_line_win32(header_text)
                    for raw_line in header_text.splitlines():
                        cleaned = raw_line.strip(" :\n")
                        if cleaned and cleaned.lower() not in seen_header:
                            header_lines.append(cleaned)
                            seen_header.add(cleaned.lower())

                    try:
                        footer_text = section.Footers(hf_type).Range.Text or ""
                    except Exception:
                        footer_text = ""
                    footer_text = clean_line_win32(footer_text)
                    for raw_line in footer_text.splitlines():
                        cleaned = raw_line.strip(" :\n")
                        if cleaned and cleaned.lower() not in seen_footer:
                            footer_lines.append(cleaned)
                            seen_footer.add(cleaned.lower())

            body_text = doc.Content.Text or ""
            body_text = clean_line_win32(body_text)

            parts = []
            if header_lines:
                parts.append("\n".join(header_lines))
            if body_text.strip():
                parts.append(body_text)
            if footer_lines:
                parts.append("\n".join(footer_lines))

            return "\n\n".join(parts).strip()

        finally:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass
            if word is not None:
                try:
                    word.Quit()
                except Exception:
                    pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _read_via_libreoffice(self, path: Path) -> str:
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            raise DependencyMissingError("LibreOffice/soffice executable not found on PATH.")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            command = [
                soffice,
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(output_dir),
                str(path.resolve()),
            ]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            docx_candidates = list(output_dir.glob("*.docx"))
            if not docx_candidates:
                raise ReaderError("LibreOffice did not output a converted .docx file.")
            
            # Read via the DocxDocumentReader we wrote
            docx_reader = DocxDocumentReader()
            doc_model = docx_reader.read(docx_candidates[0])
            return doc_model.plain_text

    def _read_via_antiword(self, path: Path) -> str:
        antiword = shutil.which("antiword")
        if not antiword:
            raise DependencyMissingError("antiword executable not found on PATH.")
        result = subprocess.run(
            [antiword, str(path.resolve())],
            check=True,
            capture_output=True,
            timeout=30,
        )
        text = result.stdout.decode("utf-8", errors="ignore")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise ReaderError("antiword returned no readable text.")
        return text

    def _read_via_binary_text_scrape(self, path: Path) -> str:
        # Try to parse via olefile to extract the WordDocument stream cleanly
        data = None
        try:
            import olefile
            if olefile.isOleFile(path):
                ole = olefile.OleFileIO(path)
                if ole.exists("WordDocument"):
                    data = ole.openstream("WordDocument").read()
        except Exception:
            pass

        if data is None:
            data = path.read_bytes()

        rtf_index = data.find(b"{\\rtf")
        if 0 <= rtf_index < 4096:
            rtf_text = data[rtf_index:].decode("cp1252", errors="ignore")
            stripped = self._strip_rtf_markup(rtf_text)
            stripped_lines = [
                line.strip()
                for line in stripped.splitlines()
                if self._looks_like_human_text(line.strip())
            ]
            if len("\n".join(stripped_lines)) >= 80:
                return "\n".join(stripped_lines)

        ascii_runs = [
            match.group(0).decode("cp1252", errors="ignore")
            for match in re.finditer(rb"[\x09\x0a\x0d\x20-\x7e\xa0-\xff]{4,}", data)
        ]
        utf16_text = data.decode("utf-16le", errors="ignore")
        utf16_runs = re.findall(r"[\t\r\n -~£]{4,}", utf16_text)

        lines: list[str] = []
        seen = set()
        for chunk in ascii_runs + utf16_runs:
            chunk = chunk.replace("\r\n", "\n").replace("\r", "\n")
            chunk = re.sub(r"[^\S\n]+", " ", chunk)
            for raw_line in chunk.splitlines():
                line = raw_line.strip(" \t\x00")
                if not self._looks_like_human_text(line):
                    continue
                key = line.lower()
                if key not in seen:
                    seen.add(key)
                    lines.append(line)

        text = "\n".join(lines)
        if len(text) < 80:
            raise ReaderError("No useful embedded DOC text found.")
        return text

    def _strip_rtf_markup(self, value: str) -> str:
        text = value
        text = re.sub(r"\\'[0-9a-fA-F]{2}", lambda m: bytes([int(m.group(0)[2:], 16)]).decode("cp1252", errors="ignore"), text)
        text = text.replace("\\rquote", "'").replace("\\lquote", "'")
        text = text.replace("\\ldblquote", '"').replace("\\rdblquote", '"')
        text = re.sub(r"\\(par|line)\b[^\S\n]*", "\n", text)
        text = re.sub(r"\\tab\b[^\S\n]*", "\t", text)
        text = re.sub(r"{\\\*\\themedata\s+[0-9A-Fa-f\s]+}", " ", text)
        text = re.sub(r"{\\\*[^{}]*(?:{[^{}]*}[^{}]*)*}", " ", text)
        text = re.sub(r"{\\(?:fonttbl|colortbl|stylesheet|listtable|listoverridetable|datastore|xmlnstbl)[\s\S]*?}\s*", " ", text)
        text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
        text = re.sub(r"\\[^a-zA-Z]", " ", text)
        text = text.replace("{", " ").replace("}", " ")
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _looks_like_human_text(self, value: str) -> bool:
        if len(value) < 2 or len(value) > 220:
            return False
        if "bjbj" in value.lower() or "\\" in value:
            return False
        if any(c in value for c in "?!%*"):
            return False
            
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 \t.,:;/-_()&'@£#\"+=<>[]\u2018\u2019\u201c\u201d\u2013\u2014\u2011áéíóúÁÉÍÓÚàèìòùÀÈÌÒÙäëïöüÄËÏÖÜâêîôûÂÊÎÔÛñÑ")
        if not all(c in allowed_chars for c in value):
            return False

        words = value.split()
        if len(words) == 1:
            w = words[0].lower()
            if not any(v in w for v in "aeiouy") and not any(c.isdigit() for c in w):
                return False

        letters = sum(ch.isalpha() for ch in value)
        digits = sum(ch.isdigit() for ch in value)
        if letters + digits < 2:
            return False
        return True

    def _build_model_from_text(self, path: Path, text: str, notes: list[str]) -> DocumentModel:
        lines_list = []
        seen = set()
        line_idx = 0
        for raw_line in text.splitlines():
            cleaned = raw_line.replace("\r", " ").replace("\t", " ").strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered not in seen:
                lines_list.append(
                    DocumentLine(
                        text=cleaned,
                        page_index=0,
                        line_index=line_idx,
                        confidence=1.0,
                    )
                )
                seen.add(lowered)
                line_idx += 1

        page = DocumentPage(
            page_index=0,
            lines=tuple(lines_list),
        )

        return DocumentModel(
            source_path=path,
            source_type="doc",
            pages=(page,),
            plain_text="\n".join(l.text for l in lines_list),
            reader_notes=tuple(notes),
            metadata={
                "raw_text": text,
                "raw_lines": text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if text else [],
            },
        )
