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
```

## 진행 상황

- [x] Phase 0 — 프로젝트 뼈대, 파일 I/O(인코딩/줄바꿈/바이너리 감지), pytest 셋업
- [x] Phase 1 — Diff 엔진(Myers 라인 diff, Alignment, 단어 단위 intraline, whitespace 분류, hunk)
- [x] Phase 2 — 파일 비교 GUI 뷰어(side-by-side, gap/색상/intraline, 스크롤 동기화, 차이 점프, 미니맵, 글꼴 줌, 열기/저장/빈 버퍼 게이팅)
- [~] Phase 3 — 병합 + 편집: 병합 버튼(→/←) + ApplyHunk 커맨드 + Undo/Redo 통합 스택 **완료**. *직접 텍스트 편집 + 편집 후 debounce 재계산은 남음*
- [ ] Phase 4 — Moved block 탐지
- [ ] Phase 5 — 폴더 비교 (M2)
- [ ] Phase 6 — 다듬기
