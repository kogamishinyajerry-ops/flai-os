"""pytest 根引导：把仓根挂上 sys.path，使 tools_impl.* 可导入。"""
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
