"""rox-merge — 파일·폴더 비교/병합 도구.

계층 구성 (PLAN §3):
- ``core``    : 순수 Python. 데이터 모델 / diff 엔진. UI·Qt 무의존.
- ``fileio``  : 파일 I/O. 인코딩·줄바꿈·바이너리 감지.
- ``app``     : 애플리케이션 계층. 세션/문서 관리, 커맨드(Undo/Redo).
- ``ui``      : PySide6 프런트엔드.
"""

__version__ = "0.2.0"
