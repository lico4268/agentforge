# ROADMAP

AgentForge 마일스톤 추적기. **세션 시작 시 이 파일을 읽고 다음 미완료 항목부터 진행**한다.
개인 메모(막힌 점·다음 할 일)는 git 제외 파일 `CLAUDE.local.md`에, 공개 진행 상태는 이 파일에 기록한다.

진행 표기: `[ ]` 미착수 · `[~]` 진행 중 · `[x]` 완료

---

## v0.1 — Run 버튼 → 백엔드 실행 → 노드 하이라이트 (거의 완료)

목표: 프론트 Run 버튼이 백엔드 실행을 트리거하고, 노드 상태가 실시간 하이라이트된다.

### 백엔드
- [x] FastAPI 앱 + CORS 설정 (`main.py`)
- [x] `GET /api/nodes` — builtin manifest 반환 (`main.py:65`, `manifests.py`)
- [x] `ws://…/ws/run` WebSocket 엔드포인트 (`main.py:137`)
- [x] `run` 메시지 수신 → `node_start` / `node_end` 이벤트 방출 (`graphs/baseline.py`, `graphs/treatment.py`)
- [x] 실행 엔진 연결 — **LangGraph로 구현**. `dispatch_graph`가 arch 이름으로 그래프 빌더에 디스패치, `graph.ainvoke`로 실행 (`main.py:107`). `harness.py` 순차 엔진/`NodeRegistry`는 사용하지 않음

### 프론트
- [x] `TransportContext.tsx` — `VITE_WS_URL` 환경변수 유무로 MockTransport ↔ WebSocketTransport 자동 전환

### 남은 확인
- [ ] 엔드투엔드 수동 검증: Run 버튼 → 노드 하이라이트 실제 동작 (`refer_data/docs/v0.1-validation.md` 기준)

> ⚠️ 아키텍처 노트: 코드는 이미 LangGraph `StateGraph` 기반이다. CLAUDE.md·AGENTS.md의
> "`NodeBase` → `nodes/__init__.py` `NodeRegistry` 등록" 규칙은 현재 구현과 맞지 않으며
> (`nodes/__init__.py`는 비어 있음), `nodes/`의 `llm_step`·`checkpoint`·`policy`는 그래프가
> 호출하는 헬퍼다. 이 문서 규칙 정합성 정리는 v0.2 항목으로 둔다.

---

## v0.2 — 안정화 / 거버넌스

- [x] 거버넌스 정비: `AGENTS.md`(규칙 단일 소스), `ROADMAP.md`(이 파일), `CLAUDE.md` 참조 링크
- [x] 백엔드 `ruff` 도입 — `pyproject.toml` `[tool.ruff]` (E/F/I/UP/B, line-length 100, isort first-party 지정)
- [x] 테스트 스캐폴딩 — `server/tests/`(pytest, 12 통과), `ui/src/__tests__/`(vitest, 4 통과) + 예시 테스트
- [x] 기존 코드 ruff 정리: 25건(import 정렬·미사용·UP·E501) 전부 해소, `ruff check` clean, 테스트 12개 유지
- [x] 에러/로깅 표준화: `make_error_event()` 헬퍼로 노드 실패 방출 단일화(`event_type="error"` + 구조화 `error{type,detail}` 필드), 프론트 `ExecutionErrorSchema`·리듀서·LogPanel 연동, `logging_config.setup_logging()` 도입
      - 결정: `node_failed` 신규 도입 대신 기존 프론트 계약(`error`→`failed`) 유지. 서버엔 `print`가 없어 "추가" 형태로 로깅 도입.
- [ ] 문서 정합성 정리: CLAUDE.md·AGENTS.md의 `NodeRegistry` 규칙을 실제 LangGraph 구조에 맞게 갱신 (또는 `harness.py`/빈 `nodes/__init__.py` 정리)

---

## v0.3+ — 동적 아키텍처 컴파일

> LangGraph 전환 자체는 v0.1에서 이미 완료. 다음은 고정 그래프 → 캔버스 그래프 동적 빌드.

- [ ] `dispatch_graph`(arch 이름 고정 분기)를 `compile(architecture)`로 교체 — 프론트 캔버스 그래프를 직접 `StateGraph`로 빌드 (`main.py:107` §8 seam)
- [ ] 임의 노드 조합 지원: 캔버스에서 만든 그래프를 실행
- [ ] 체크포인트·정책 노드를 동적 그래프에 통합

---

## 참고 스펙 문서

- 전체 기획: `refer_data/docs/agentforge.md`
- 백엔드 스펙: `refer_data/docs/backend-spec.md`
- 노드 스펙: `refer_data/docs/node-spec.md`
- UI 아키텍처: `refer_data/docs/ui-architecture.md`
