"""Small console helper called by the native menu-scene bridge."""
import sys
from pathlib import Path
if not getattr(sys, 'frozen', False):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.frontend_stadium import main
if __name__ == '__main__':
    raise SystemExit(main())
