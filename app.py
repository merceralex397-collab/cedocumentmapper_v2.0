import sys
from pathlib import Path

# Add the 'src' directory to the Python path to resolve imports locally
src_path = str(Path(__file__).resolve().parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from cedocumentmapper_v2.ui import start_webview

if __name__ == "__main__":
    # Check if we should run in debug/dev mode (e.g. loading dev-server URL)
    debug_mode = "--dev" in sys.argv or "--debug" in sys.argv
    start_webview(debug=debug_mode)
