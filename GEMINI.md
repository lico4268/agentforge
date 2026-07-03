# Agentforge — Gemini Context

> 코딩·린트·import·타입 계약 규칙의 단일 소스는 **AGENTS.md**다. 반드시 먼저 읽을 것.
> 프로젝트 구조·환경 설정은 **CLAUDE.md** 참고.

---

## 프로젝트 요약

ComfyUI 스타일의 에이전트 아키텍처 빌더. 노드 캔버스에서 LLM 에이전트 파이프라인을 시각적으로 설계하고 실행한다.

- **백엔드**: FastAPI + LangGraph (Python 3.12, `server/`)
- **프론트**: React + TypeScript + Vite (`ui/`)
- **WebSocket 연동**: `ws://localhost:8000/ws/run`

```
프론트 캔버스 (React Flow)
    │ WebSocket
    ▼
백엔드 WS 핸들러 (main.py)
    │ dispatch_graph(arch_name)
    ▼
LangGraph StateGraph (graphs/*.py)
    │ emit(make_event(...))
    ▼
프론트 노드 상태 업데이트
```

---

## 현재 진행 상태 (2026-07-03 기준)

- **v0.1**: 거의 완료. E2E 수동 검증 1건 남음 (ANTHROPIC_API_KEY 401 해소 후)
- **v0.2**: 완료 (거버넌스/ruff/테스트/에러·로깅 표준화)
- **v0.3**: 미착수. 핵심 = `compile_graph(architecture: dict)` 구현
  - `server/main.py:110`의 `dispatch_graph`가 차단 지점
  - `current canvas` 선택 시 ValueError 발생 — 여기가 seam

### v0.3 작업 진입 지점

```python
# server/main.py:110 근처
# dispatch_graph(arch_name) 에 compile_graph fallback 연결 필요
```

---

## 핵심 설계 결정 (변경하지 말 것)

### Policy 노드 (Phase 1 구현 완료, 미커밋)
- `confidence` 자기채점 라우팅 **폐기** → `ReviewDelta` 기반 의도정합성 리뷰
- `review_branch` 필드: `accept` / `refine` / `clarify`
- `score` 필드 없음 — confidence 재림 방지
- 관련 파일: `server/nodes/review.py`, `server/nodes/policy.py`, `server/models.py`

### 타입 계약
- 백엔드 Pydantic ↔ 프론트 Zod 스키마: **camelCase 통일** (snake_case 변환 레이어 없음)
- WS 페이로드는 `events.py`의 `to_frontend()`를 통해 나감

### 노드 추가 규칙
- **폐기된 방식**: `NodeBase` / `NodeRegistry` (구현 없음)
- **현행 방식**: `server/nodes/`에 함수 → `server/graphs/`의 `StateGraph.add_node()`
- 프론트: `server/manifests.py`의 `BUILTIN_MANIFESTS`에 manifest(dict) 추가

---

## 개발 환경

```bash
./start.sh          # 백엔드(8000) + 프론트(5173) 동시 시작
```

환경변수: `server/.env`에 `ANTHROPIC_API_KEY` 필수.

---

## 하지 말아야 할 것

- `confidence` 기반 라우팅 복원 (폐기된 설계)
- `NodeBase` / `NodeRegistry` 방식으로 노드 추가
- snake_case ↔ camelCase 변환 레이어 추가
- `print()` 사용 (대신 `from logging_config import logger`)
- 코드 없이 `# TODO` / `# removed` 주석만 남기기
