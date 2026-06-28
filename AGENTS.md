# AGENTS.md

AI 코딩 에이전트(Claude Code, Cursor, Antigravity 등)가 **이 저장소에서 코드를 작성·수정할 때 항상 따르는 규칙**의 단일 소스다.
아키텍처·디렉토리·실행 방법은 [CLAUDE.md](./CLAUDE.md)를, 진행 상태는 [ROADMAP.md](./ROADMAP.md)를 참고한다.

---

## 1. 경로

- 파일 참조·도구 호출 시 **항상 절대 경로**를 사용한다.
- 작업 디렉토리 가정에 의존하지 않는다 (`cd` 후 상대 경로 ❌).

## 2. 수정 후 검증 (필수)

코드를 변경했으면 커밋·완료 보고 전에 해당 영역의 검사를 **반드시 실행**한다.

| 영역 | 명령 (해당 디렉토리에서) |
|------|--------------------------|
| 백엔드 (`server/`) | `ruff check .` → `ruff format .` |
| 프론트 (`ui/`) | `npm run lint` (oxlint) → `npm run build`(`tsc -b`)로 타입 확인 |
| 테스트 | 백엔드 `pytest`, 프론트 `npm run test`(도입 후) |

- 린트 에러는 남기지 않는다. 자동 수정 가능한 항목은 `ruff check --fix`로 정리.

## 3. import 순서

- **백엔드**: ruff의 isort 규칙(`I`)을 따른다 — 표준 라이브러리 → 서드파티 → 로컬, 그룹 사이 빈 줄. `ruff check --fix`가 정렬한다.
- **프론트**: oxlint 기준을 따르고, 외부 패키지 → 내부 모듈(`@/…` 또는 상대경로) 순으로 그룹화한다.

## 4. 타입 계약 (백엔드 ↔ 프론트)

- 백엔드 Pydantic 필드명과 프론트 Zod 스키마는 **camelCase로 통일**한다. snake_case ↔ camelCase 변환 레이어를 두지 않는다.
- WebSocket으로 나가는 페이로드는 `events.py`의 `to_frontend()`(camelCase)를 거친다. 새 필드 추가 시 백엔드 직렬화와 프론트 `ui/src/types/`의 Zod 스키마를 **동시에** 갱신한다.

## 5. 노드 추가 규칙

- `server/nodes/`에 `NodeBase`를 구현하고 `server/nodes/__init__.py`의 `NodeRegistry`에 등록한다.
- 이벤트 `output` 필드는 Inspector에 JSON으로 그대로 표시되므로 직렬화 가능한 형태(`str`, `dict`, `list`)만 넣는다.

## 6. 테스트 (권장)

- 기능을 추가·수정하면 가능하면 **같은 PR에 테스트를 동반**한다. 백엔드는 `server/tests/`(pytest), 프론트는 `ui/src/__tests__/`(vitest).
- 외부 LLM API 호출은 테스트에서 **목(mock)** 처리한다. 네트워크·실API 키에 의존하는 테스트는 만들지 않는다.

## 7. 에러·로깅 (표준화)

- 노드 실행 실패는 산발적으로 처리하지 말고, 표준 실패 이벤트 경로(`event_type="node_failed"`)로 일관되게 방출한다. 자세한 형식은 ROADMAP의 에러 표준화 항목 진행에 따른다.
- `print` 대신 표준 `logging`을 사용하고 레벨은 `config.LOG_LEVEL`을 따른다.
