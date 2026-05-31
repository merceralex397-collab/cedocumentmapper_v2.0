from pathlib import Path
import pytest
from cedocumentmapper_v2.readers import get_reader_for_path
from cedocumentmapper_v2.domain.models import DocumentModel

INSTRUCTIONS_DIR = Path("c:/Users/PC/Documents/GitHub/cedocumentmapper/docs/Instructions")


@pytest.mark.skipif(not INSTRUCTIONS_DIR.exists(), reason="v1 Instructions directory not found")
def test_pdf_reader():
    pdf_path = INSTRUCTIONS_DIR / "ALISON PDF 01.pdf"
    assert pdf_path.exists()
    
    reader = get_reader_for_path(pdf_path)
    model = reader.read(pdf_path)
    
    assert isinstance(model, DocumentModel)
    assert model.source_type == "pdf"
    assert len(model.pages) > 0
    print("\nPLAIN TEXT PEEK:", model.plain_text[:500])
    assert len(model.plain_text.strip()) > 0
    # Let's check for "ALISON" or similar instead
    assert any("alison" in line.text.lower() or "claim" in line.text.lower() for page in model.pages for line in page.lines)


@pytest.mark.skipif(not INSTRUCTIONS_DIR.exists(), reason="v1 Instructions directory not found")
def test_docx_reader():
    docx_path = INSTRUCTIONS_DIR / "ALISON WORD 01.docx"
    assert docx_path.exists()
    
    reader = get_reader_for_path(docx_path)
    model = reader.read(docx_path)
    
    assert isinstance(model, DocumentModel)
    assert model.source_type == "docx"
    assert len(model.pages) == 1
    assert len(model.plain_text.strip()) > 0


@pytest.mark.skipif(not INSTRUCTIONS_DIR.exists(), reason="v1 Instructions directory not found")
def test_msg_reader():
    msg_path = INSTRUCTIONS_DIR / "FW 01.msg"
    assert msg_path.exists()
    
    reader = get_reader_for_path(msg_path)
    model = reader.read(msg_path)
    
    assert isinstance(model, DocumentModel)
    assert model.source_type == "msg"
    assert len(model.pages) == 1
    assert len(model.plain_text.strip()) > 0
    assert any("Subject:" in line.text for line in model.pages[0].lines)


def _is_doc_supported():
    import shutil
    if shutil.which("soffice") or shutil.which("libreoffice") or shutil.which("antiword"):
        return True
    try:
        import win32com.client
        # Try to initialize COM and check if Word is dispatchable
        import pythoncom
        pythoncom.CoInitialize()
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Quit()
            return True
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass
    return False


@pytest.mark.skipif(not INSTRUCTIONS_DIR.exists() or not _is_doc_supported(), reason="DOC reading dependencies not available")
def test_doc_reader():
    doc_path = INSTRUCTIONS_DIR / "ALS 01.DOC"
    assert doc_path.exists()
    
    reader = get_reader_for_path(doc_path)
    model = reader.read(doc_path)
    
    assert isinstance(model, DocumentModel)
    assert model.source_type == "doc"
    assert len(model.pages) == 1
    assert len(model.plain_text.strip()) > 0


