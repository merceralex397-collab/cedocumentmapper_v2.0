from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Optional

def _windows_known_folder_path(folder_guid: str) -> Optional[Path]:
    """Resolve a Windows KNOWNFOLDERID to its actual current path."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # Parse "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}" into _GUID.
        clean = folder_guid.strip("{}")
        parts = clean.split("-")
        if len(parts) != 5:
            return None
        guid = _GUID()
        guid.Data1 = int(parts[0], 16)
        guid.Data2 = int(parts[1], 16)
        guid.Data3 = int(parts[2], 16)
        rest = bytes.fromhex(parts[3] + parts[4])
        for i, byte in enumerate(rest):
            guid.Data4[i] = byte

        SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
        SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        SHGetKnownFolderPath.restype = ctypes.HRESULT

        out_ptr = ctypes.c_wchar_p()
        result = SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out_ptr))
        if result != 0 or not out_ptr.value:
            return None
        path = Path(out_ptr.value)
        # Free the buffer Windows allocated for us.
        ctypes.windll.ole32.CoTaskMemFree(out_ptr)
        return path if path.exists() else None
    except Exception:
        return None

_FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
_FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"

def get_documents_dir() -> Path:
    resolved = _windows_known_folder_path(_FOLDERID_DOCUMENTS)
    if resolved is not None:
        return resolved
    home = Path.home()
    docs = home / "Documents"
    return docs if docs.exists() else home

def get_desktop_dir() -> Path:
    resolved = _windows_known_folder_path(_FOLDERID_DESKTOP)
    if resolved is not None:
        return resolved
    home = Path.home()
    desktop = home / "Desktop"
    return desktop if desktop.exists() else home

APP_DATA_DIR = get_documents_dir() / "CE Document Mapper"
OUTPUT_DIR = get_desktop_dir()

def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = value.strip().replace(" ", "_")
    return value or "export"

def unique_output_path(directory: Path, base_name: str, extension: str) -> Path:
    candidate = directory / f"{base_name}{extension}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = directory / f"{base_name}_{index}{extension}"
        if not candidate.exists():
            return candidate
        index += 1
