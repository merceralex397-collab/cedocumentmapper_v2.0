from __future__ import annotations

import re
from pathlib import Path
from email import policy
from email.parser import BytesParser
from html import unescape as html_unescape

import extract_msg

from cedocumentmapper_v2.domain.models import (
    DocumentModel,
    DocumentPage,
    DocumentLine,
)
from cedocumentmapper_v2.readers.base import DocumentReader
from cedocumentmapper_v2.readers.errors import ReaderError


class EmailDocumentReader(DocumentReader):
    supported_extensions: frozenset[str] = frozenset([".eml", ".msg"])

    def read(self, path: Path) -> DocumentModel:
        if not path.exists():
            raise ReaderError(f"File not found: {path}")

        ext = path.suffix.lower()
        notes = []

        try:
            if ext == ".eml":
                text, reader_notes = self._read_eml(path)
                notes.extend(reader_notes)
            elif ext == ".msg":
                text, reader_notes = self._read_msg(path)
                notes.extend(reader_notes)
            else:
                raise ReaderError(f"Unsupported email format: {ext}")
        except Exception as exc:
            raise ReaderError(f"Could not read email: {exc}") from exc

        # Create single page for email documents
        lines_list = []
        seen = set()
        for idx, raw_line in enumerate(text.splitlines()):
            cleaned = raw_line.replace("\r", " ").replace("\t", " ").strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered not in seen:
                lines_list.append(
                    DocumentLine(
                        text=cleaned,
                        page_index=0,
                        line_index=idx,
                        confidence=1.0,
                    )
                )
                seen.add(lowered)

        page = DocumentPage(
            page_index=0,
            lines=tuple(lines_list),
        )

        return DocumentModel(
            source_path=path,
            source_type="eml" if ext == ".eml" else "msg",
            pages=(page,),
            plain_text="\n".join(l.text for l in lines_list),
            reader_notes=tuple(notes),
            metadata={
                "raw_text": text,
                "raw_lines": text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if text else [],
                "email_source_type": ext.lstrip("."),
            },
        )

    def _read_eml(self, path: Path) -> tuple[str, list[str]]:
        notes = ["Read EML using email standard parser."]
        with open(path, "rb") as fh:
            msg = BytesParser(policy=policy.default).parse(fh)

        parts = []
        for header in ("Subject", "From", "To", "Date"):
            value = msg.get(header)
            if value:
                parts.append(f"{header}: {value}")
        if parts:
            parts.append("")

        body_parts = []
        html_parts = []
        if msg.is_multipart():
            for part in msg.walk():
                disposition = str(part.get_content_disposition() or "").lower()
                if disposition == "attachment":
                    continue
                ctype = part.get_content_type()
                try:
                    payload = part.get_content()
                except Exception:
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            payload = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                    except Exception:
                        payload = ""
                if not isinstance(payload, str):
                    continue
                if ctype == "text/plain":
                    body_parts.append(payload)
                elif ctype == "text/html":
                    html_parts.append(payload)
        else:
            payload = msg.get_content()
            if isinstance(payload, str):
                if msg.get_content_type() == "text/html":
                    html_parts.append(payload)
                else:
                    body_parts.append(payload)

        body = "\n\n".join(part.strip() for part in body_parts if part and part.strip())
        if not body and html_parts:
            body = "\n\n".join(self._strip_html_tags(part) for part in html_parts if part and part.strip())
        if body:
            parts.append(body.strip())

        text = "\n".join(parts)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip(), notes

    def _read_msg(self, path: Path) -> tuple[str, list[str]]:
        notes = ["Read MSG using extract_msg."]
        msg = extract_msg.Message(str(path))  # type: ignore[no-untyped-call]

        def _coerce(value: object) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                for encoding in ("utf-8", "cp1252", "latin-1"):
                    try:
                        return value.decode(encoding).replace("\x00", "").strip()
                    except UnicodeDecodeError:
                        continue
                return value.decode("utf-8", errors="ignore").replace("\x00", "").strip()
            return str(value).replace("\x00", "").strip()

        try:
            parts = []
            for label, attr in (
                ("Subject", "subject"),
                ("From", "sender"),
                ("To", "to"),
                ("Cc", "cc"),
                ("Date", "date"),
            ):
                try:
                    value = _coerce(getattr(msg, attr, None))
                except Exception:
                    value = ""
                if value:
                    parts.append(f"{label}: {value}")
            if parts:
                parts.append("")

            # Body processing
            body = ""
            try:
                body = _coerce(getattr(msg, "body", None))
            except Exception:
                pass

            def _looks_like_html(text: str) -> bool:
                if not text:
                    return False
                head = text.lstrip()[:200].lower()
                return ("<html" in head or "<body" in head or "<!doctype" in head
                        or "<o:p" in head or "<v:" in head)

            if body and _looks_like_html(body):
                body = self._strip_html_tags(body)
            
            if not body:
                try:
                    html = _coerce(getattr(msg, "htmlBody", None))
                    if html:
                        body = self._strip_html_tags(html)
                except Exception:
                    pass

            if not body:
                try:
                    rtf_bytes = getattr(msg, "rtfBody", None)
                    if rtf_bytes:
                        if isinstance(rtf_bytes, bytes):
                            rtf_text = rtf_bytes.decode("utf-8", errors="ignore")
                        else:
                            rtf_text = str(rtf_bytes)
                        body = self._strip_rtf_markup(rtf_text)
                except Exception:
                    pass

            if body:
                parts.append(body.strip())

            # Attachments
            attachment_names = []
            try:
                attachments = list(getattr(msg, "attachments", []) or [])
                for att in attachments:
                    name = ""
                    for candidate_attr in ("longFilename", "shortFilename", "displayName"):
                        try:
                            candidate = getattr(att, candidate_attr, None)
                        except Exception:
                            candidate = None
                        if candidate is not None:
                            name = _coerce(candidate)
                            if name:
                                break
                    if name:
                        attachment_names.append(name)
            except Exception:
                pass

            if attachment_names:
                parts.append("")
                parts.append("Attachments: " + ", ".join(attachment_names))

            text = "\n".join(parts)
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip(), notes

        finally:
            msg.close()

    @staticmethod
    def _strip_html_tags(value: str) -> str:
        if not value:
            return ""

        cp1252_singles = {
            "\x91": "'", "\x92": "'", "\x93": '"', "\x94": '"',
            "\x96": "-", "\x97": "-", "\x85": "...",
        }
        for raw, replacement in cp1252_singles.items():
            value = value.replace(raw, replacement)

        value = re.sub(r"<style[^>]*>.*?</style\s*>", " ", value, flags=re.I | re.S)
        value = re.sub(r"<script[^>]*>.*?</script\s*>", " ", value, flags=re.I | re.S)
        value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
        value = re.sub(r"<\?xml[^>]*\?>", " ", value, flags=re.I)
        value = re.sub(r"<!doctype[^>]*>", " ", value, flags=re.I)

        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
        value = re.sub(r"</(p|div|tr|li|h[1-6])\s*>", "\n", value, flags=re.I)
        value = re.sub(r"</td\s*>", "\t", value, flags=re.I)
        value = re.sub(r"<[^>]+>", " ", value)

        value = html_unescape(value)
        value = value.replace("\u00a0", " ")
        value = value.replace("\x00", "")

        value = re.sub(r"\n{3,}", "\n\n", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        return value.strip()

    @staticmethod
    def _strip_rtf_markup(rtf: str) -> str:
        if not rtf:
            return ""
        text = re.sub(r"\\bin\d+\s+\S*", " ", rtf)
        text = re.sub(r"\\'([0-9A-Fa-f]{2})",
                      lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", errors="ignore"),
                      text)
        text = re.sub(r"\\[a-zA-Z]+-?\d*\s?", " ", text)
        text = re.sub(r"\\[^a-zA-Z]", "", text)
        text = text.replace("{", " ").replace("}", " ")
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
