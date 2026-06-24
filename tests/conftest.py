"""pytest 공통 설정.

src 레이아웃(`src/hedonic`)을 editable 설치 없이도 import할 수 있도록
`src` 디렉터리를 sys.path에 추가한다.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
