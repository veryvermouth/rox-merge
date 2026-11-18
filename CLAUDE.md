# rox-merge

PySide6 기반 파일·폴더 비교/병합 도구. 기능 요약은 [README.md](README.md), 설계는 [docs/PLAN.md](docs/PLAN.md), 변경 이력은 [CHANGELOG.md](CHANGELOG.md).

## 공통 규칙 (먼저 읽기)

공통 규칙의 원본은 비공개 저장소 `veryvermouth/claude-config`의 `global/CLAUDE.md`다.
작업을 시작하기 전에 그 파일을 먼저 읽고, 이 파일의 규칙과 부딪히면 그쪽을 따른다.

- 이미 불러와져 있으면(제목 "공통 규칙 (모든 세션)"이 컨텍스트에 있으면) 다시 읽지 않는다.
  로컬 PC 세션은 보통 전역 설정(`~/.claude/CLAUDE.md`)에서 불러와져 있다.
- 불러와져 있지 않으면(주로 클라우드 세션) 아래 순서로 읽는다.
  1. 세션에 연결된 저장소에 `veryvermouth/claude-config`가 없으면, 먼저 저장소 추가 도구(예: `add_repo`)로 읽기 권한으로 추가한다.
     클라우드 세션은 처음에 자기 저장소에만 접근할 수 있어서, 추가하기 전에는 파일 읽기 도구·`gh`·`git` 모두 거부된다.
     추가하기 전에 `gh`나 `git`으로 접근을 미리 시험하지 않는다.
  2. 추가한 뒤 GitHub 파일 읽기 도구(owner `veryvermouth`, repo `claude-config`, path `global/CLAUDE.md`)로 읽는다.
  3. 그 도구가 없으면 그 세션에서 쓸 수 있는 다른 방법(`git clone` 등)으로 읽는다. 세션 규칙이 막는 방법은 쓰지 않는다.
- 사용자가 "공통 규칙 다시 읽어 줘"라고 하거나 공통 규칙이 바뀌었다고 하면, 이미 읽었더라도 최신 main에서 다시 읽고 새 내용을 따른다.
- 읽지 못했으면 사용자에게 그렇다고 알리고, 적어도 아래 핵심 규칙은 지킨다.
  - 답변은 항상 한국어로 한다.
  - main(기본 브랜치)에 직접 커밋·푸시하지 않는다. 작업 브랜치를 만들고 PR을 연다.
  - 병합 전에 "main에 병합할까요?"를 묻고, 사용자가 그렇다고 하거나 직접 병합하라고 할 때만 병합한다.
  - 병합은 squash 방식으로 한다.

## 이 저장소 규칙

공통 규칙에 더해 rox-merge에서만 지키는 것.

- **공개 저장소다.** 비밀번호, API 키, 토큰, 개인정보, 회사 내부 파일을 커밋하지 않는다. `examples/`에 예시 파일을 넣을 때도 확인한다.
- 테스트는 화면 없이 돌린다: `QT_QPA_PLATFORM=offscreen python -m pytest -q`. 커밋 전에 통과하는지 확인한다.
- 사용자에게 보이는 기능을 바꾸면 `CHANGELOG.md`(Keep a Changelog 형식)와 README의 기능 요약도 함께 고친다.
