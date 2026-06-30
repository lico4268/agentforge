# ROADMAP

AgentForge 마일스톤 추적기. **세션 시작 시 이 파일을 읽고 다음 미완료 항목부터 진행**한다.
개인 메모(막힌 점·다음 할 일)는 git 제외 파일 `CLAUDE.local.md`에, 공개 진행 상태는 이 파일에 기록한다.

진행 표기: `[ ]` 미착수 · `[~]` 진행 중 · `[x]` 완료

---

## v0.1 — Run 버튼 → 백엔드 실행 → 노드 하이라이트 (거의 완료)

목표: 프론트 Run 버튼이 백엔드 실행을 트리거하고, 노드 상태가 실시간 하이라이트된다.

### 백엔드
- [x] FastAPI 앱 + CORS 설정 (`main.py`)
- [x] `GET /api/nodes` — builtin manifest 반환 (`main.py:68`, `manifests.py`)
- [x] `GET /api/models` — `config.yaml` 기반 모델 목록, API 키 미설정 시 `available=false` (`main.py:62`)
- [x] `GET|POST /api/architectures` + `GET /api/architectures/{id}` — 아키텍처 JSON 파일 저장/로드 (`main.py:73~99`)
- [x] `ws://…/ws/run` WebSocket 엔드포인트 (`main.py:140`)
- [x] `run` 메시지 수신 → `node_start` / `node_end` 이벤트 방출 (`graphs/baseline.py`, `graphs/treatment.py`)
- [x] `resume` 메시지 수신 → LangGraph `Command(resume=decision)` 재개 (Human Checkpoint) (`main.py:195`)
- [x] `reconnect` 메시지 수신 → 누적 이벤트 스냅샷 재전송 (`main.py:222`)
- [x] 실행 엔진 연결 — **LangGraph로 구현**. `dispatch_graph`가 arch 이름으로 그래프 빌더에 디스패치, `graph.ainvoke`로 실행 (`main.py:110`). `harness.py` 순차 엔진/`NodeRegistry`는 사용하지 않음
- [x] `config.yaml` — 서버/모델/실행 파라미터 중앙 설정 파일 (CORS, pass_threshold, max_retries 등)

### 프론트
- [x] `TransportContext.tsx` — `VITE_WS_URL` 환경변수 유무로 MockTransport ↔ WebSocketTransport 자동 전환
- [x] `Toolbar` — 태스크 입력, 아키텍처 선택(`gsm8k-baseline` / `gsm8k-treatment` / `current canvas`), 모델 선택, Run 버튼, 결과/에러 배너
- [x] `NodeLibrary` 사이드바 — 카테고리별 노드 카드, 드래그로 캔버스에 추가
- [x] `LogPanel` — 실시간 실행 이벤트 스트림 로그
- [x] `GenericNode` — 노드 상태(running/success/failed/skipped) 테두리·뱃지 시각화, ModelSlots 임베드
- [x] `Inspector` — 노드 설정 편집, ModelSlots 편집, 연결 목록, Last I/O, 실행 메트릭
- [x] `ModelSlots` — 노드 내 인라인 모델 슬롯 UI (Inspector 편집 + GenericNode 표시)
- [x] `useGraphStore` — 노드/엣지 CRUD, `loadArchitecture` / `toArchitecture` 직렬화
- [x] `useExecutionStore` — 실행 이벤트 리덕션, 노드별 런타임 상태(callCount, totalDurationMs, totalTokens, policyDecision)

### 남은 확인
- [ ] 엔드투엔드 수동 검증: Run 버튼 → 노드 하이라이트 실제 동작 (`refer_data/docs/v0.1-validation.md` 기준)

> ✅ 아키텍처 노트 (v0.2에서 문서 정합성 정리 완료): 코드는 v0.1부터 LangGraph `StateGraph` 기반이다.
> `nodes/`의 `llm_step`·`checkpoint`·`policy`는 그래프가 호출하는 헬퍼 함수이고,
> `nodes/__init__.py`는 빈 패키지 마커다 (`NodeBase`/`NodeRegistry` 미존재). `harness.py`는
> 순차 실행 엔진이 아니라 벤치마크 하니스(`run_dataset`+`gsm8k_grader`+`Report`)다.
> CLAUDE.md·AGENTS.md를 실제 구조에 맞게 갱신 완료.

---

## v0.2 — 안정화 / 거버넌스

- [x] 거버넌스 정비: `AGENTS.md`(규칙 단일 소스), `ROADMAP.md`(이 파일), `CLAUDE.md` 참조 링크
- [x] 백엔드 `ruff` 도입 — `pyproject.toml` `[tool.ruff]` (E/F/I/UP/B, line-length 100, isort first-party 지정)
- [x] 테스트 스캐폴딩 — `server/tests/`(pytest, 12 통과), `ui/src/__tests__/`(vitest, 4 통과) + 예시 테스트
- [x] 기존 코드 ruff 정리: 25건(import 정렬·미사용·UP·E501) 전부 해소, `ruff check` clean, 테스트 12개 유지
- [x] 에러/로깅 표준화: `make_error_event()` 헬퍼로 노드 실패 방출 단일화(`event_type="error"` + 구조화 `error{type,detail}` 필드), 프론트 `ExecutionErrorSchema`·리듀서·LogPanel 연동, `logging_config.setup_logging()` 도입
      - 결정: `node_failed` 신규 도입 대신 기존 프론트 계약(`error`→`failed`) 유지. 서버엔 `print`가 없어 "추가" 형태로 로깅 도입.
- [x] 문서 정합성 정리: CLAUDE.md(디렉토리 트리·연동 다이어그램·개발 규칙)·AGENTS.md(§5 노드 추가 규칙)를 실제 LangGraph 구조에 맞게 갱신. 폐기된 `NodeBase`/`NodeRegistry` 규칙 제거, `harness.py`=벤치마크 하니스로 정정, `models_config.json`→`config.yaml` 반영, 노드 추가 절차를 "그래프 헬퍼 + manifest 등록"으로 재정의

---

## v0.3 — 동적 아키텍처 컴파일 (다음 목표)

> LangGraph 전환 자체는 v0.1에서 이미 완료. 다음은 고정 그래프 → 캔버스 그래프 동적 빌드.

### 현재 상황
- 프론트 Toolbar에 `current canvas` 옵션이 이미 있음 — `toArchitecture('current-canvas')` 직렬화 후 WS로 전송
- 백엔드 `dispatch_graph`는 `'gsm8k-baseline'` / `'gsm8k-treatment'`만 인식; 나머지는 `ValueError` → 현재 'current canvas'로 Run 누르면 에러

### 할 일
- [ ] `compile_graph(architecture: dict) -> CompiledGraph` 함수 구현
  - `architecture.nodes`의 `type`(manifest type)을 LangGraph 노드로 매핑
  - `architecture.edges`로 `StateGraph` 엣지 연결
  - `policy.review` 노드의 conditional edge (`pass`/`auto`/`human`) 처리
  - `human.checkpoint` 노드의 `interrupt_before` 처리
- [ ] `dispatch_graph`에 `compile_graph` fallback 연결 (`main.py:110` seam)
- [ ] 프론트 `starterArchitecture.ts` → 캔버스에서 직접 실행 가능하도록 검증
- [ ] 임의 노드 조합 지원 (캔버스에서 만든 그래프를 실행)

### v0.4+ 이후
- [ ] GSM8K 100~200문제 배치 실행 — Baseline vs Treatment pass@1 비교 (`refer_data/docs/v0.1-validation.md` §5)
- [ ] Human Checkpoint 프론트 UI — 실행 일시정지 + 사용자 decision 입력 → `resume` 메시지 전송
- [ ] Architecture 저장/불러오기 UI — Toolbar에서 `/api/architectures` 연동
- [ ] τ²-bench 연동 (정책 준수 벤치마크) — v0.1 기획 문서 §4 참고

---

## 참고 스펙 문서

- 전체 기획: `refer_data/docs/agentforge.md`
- 백엔드 스펙: `refer_data/docs/backend-spec.md`
- 노드 스펙: `refer_data/docs/node-spec.md`
- UI 아키텍처: `refer_data/docs/ui-architecture.md`
