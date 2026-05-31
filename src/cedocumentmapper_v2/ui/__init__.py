from __future__ import annotations

from typing import Any

__all__ = ["start_webview", "WebviewBridge"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .host import WebviewBridge, start_webview

        return {"start_webview": start_webview, "WebviewBridge": WebviewBridge}[name]
    raise AttributeError(name)
