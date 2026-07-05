# rox-merge

Araxis Merge 류의 파일·폴더 비교/병합 도구 (PySide6 기반).

설계/계획은 [docs/PLAN.md](docs/PLAN.md) 참조.

## 패키지 구조

```
src/rox_merge/
  core/       # 순수 Python. UI/Qt 무의존. 데이터 모델·diff 엔진(예정)
  fileio/     # 파일 I/O: 인코딩·줄바꿈·바이너리 감지
  app/        # 애플리케이션 계층: 세션/문서 관리, 커맨드(예정)
  ui/         # PySide6 UI (예정)
tests/        # pytest 단위 테스트
```

## 개발 환경

```bash
python -m pip install -e ".[dev]"   # 의존성 + 개발 도구(pytest)
pytest                               # 테스트 실행
python -m rox_merge                  # GUI 실행 (선택: 좌/우 파일 경로 2개)
python -m rox_merge left.py right.py
python -m rox_merge dir_a dir_b      # 인자가 폴더 2개면 폴더 비교 창
```

실행 후에는 툴바의 **"파일 비교"/"폴더 비교"**(Ctrl+N / Ctrl+D) 버튼으로 두 모드를 오갈 수 있다.

## 진행 상황

- [x] Phase 0 — 프로젝트 뼈대, 파일 I/O(인코딩/줄바꿈/바이너리 감지), pytest 셋업
- [x] Phase 1 — Diff 엔진(Myers 라인 diff, Alignment, 단어 단위 intraline, whitespace 분류, hunk)
- [x] Phase 2 — 파일 비교 GUI 뷰어(side-by-side, gap/색상/intraline, 스크롤 동기화, 차이 점프, 미니맵, 글꼴 줌, 열기/저장/빈 버퍼 게이팅)
- [x] Phase 3 — 병합 + 편집: 병합 버튼(→/←) + ApplyHunk 커맨드, 직접 텍스트 편집(커서/키 입력), Undo/Redo 통합 스택, 편집 후 debounce(150ms) 재계산
- [x] Phase 4 — Moved block 탐지(해시 매칭, 최소 3라인·기본 ON, 전용 보라색 + 연결선, 툴바 토글)
- [x] Phase 5 — 폴더 비교(재귀 비교 엔진 + 상태 분류, 빠른/정확(해시) 토글, 좌/우 대응 트리, 다른 항목만 필터, 차이 있는 곳만 초기 확장, Ctrl+]/[/0, 분할 모드 ↔ 새 탭 모드 토글, 더블클릭→diff 편집)
- [ ] Phase 6 — 다듬기
