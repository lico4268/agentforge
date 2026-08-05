# Radial Agent Canvas — Implementation Plan

## 목표

원형 agent node와 방사형 배치를 도입해 캔버스가 직렬 파이프라인보다 agent 간 관계·분기·되먹임을 먼저 보여주게 한다. 이 작업은 현재 LangGraph 실행 계약을 변경하지 않는다.

## 불변 계약

- `Architecture`의 `version`, node(`id`, `type`, `position`, `config`), edge(`id`, `source`, `sourceHandle`, `target`, `targetHandle`)를 유지한다.
- `sourceHandle` 기반 Review/Human 분기와 `compile_graph()` 동작을 유지한다.
- layout/renderer 전용 정보는 Architecture JSON에 넣지 않는다.
- topology graph store와 execution store 분리를 유지한다.

## Slice 0 — 기준선 및 계약 고정 (완료: 2026-08-04)

작업:

- 서버 manifest와 `ui/src/registry/builtinManifests.ts`의 Planning/Reasoning 계약 차이를 점검·정리한다.
- `load → serialize`에서 node config·edge handle이 보존되는 프론트 회귀 테스트를 추가한다.
- 같은 topology에 서로 다른 좌표를 적용해도 backend compile 결과가 같음을 검증한다.

수용 기준:

- layout/renderer 필드가 `toArchitecture()` 결과에 없다.
- position 외 node/edge 계약이 보존된다.
- 기존 전체 프론트·백엔드 검사가 통과한다.

## Slice 1 — 이중 renderer와 checkpoint 액션 (완료: 2026-08-04)

작업:

- 기존 `GenericNode`는 남기고 `AgentNode`를 병행한다.
- UI 상태에 `classic | agent` canvas mode를 둔다. 저장 Architecture에는 포함하지 않는다.
- Human Checkpoint의 Approve/Revise/Reject를 Inspector에서도 실행 가능하게 공통 컴포넌트로 추출한다.

수용 기준:

- mode 전환이 topology/config/선택 상태를 바꾸지 않는다.
- manifest custom component가 두 mode 모두 우선한다.
- paused checkpoint를 Inspector에서 resume할 수 있다.

## Slice 2 — 원형 AgentNode와 원주형 port (완료: 2026-08-04)

작업:

- `AgentNode.tsx`에 아이콘·짧은 이름·상태 ring·모델 요약 badge만 표시한다.
- 신규 `RadialNodePorts.tsx`에서 input은 왼쪽 반원, output은 오른쪽 반원에 균등 배치한다.
- 상태를 색만으로 표현하지 않고 icon/text/focus 상태를 병행한다. reduced-motion을 지원한다.

수용 기준:

- 기존 manifest port ID와 edge handle 직렬화가 유지된다.
- 0~다수 port에서 겹침 없이 연결할 수 있다.
- Review의 `accept/refine/clarify`가 독립 handle로 남는다.

> **개정 완료 (2026-08-05, 같은 날 두 차례 개정)**: 위 좌/우 고정 반원 배치가 되먹임 edge 교차 문제의
> 원인으로 확인됨(Fable 검증) → hub/rim 반구 배정 + 반구 내 파트너 각도 편향으로 1차 대체. 하지만
> 사용자가 실제로 써보고 "포트 점 자체가 헷갈리고 선도 겹치고 방향 파악이 안 된다"고 확인 → **점을
> 기본적으로 숨기고(방향은 edge 화살표로만 읽음), input/output 반구 구분 없이 노드 전체 360도를
> 파트너 방향으로 편향 배치**하는 쪽으로 2차 대체. hub/rim 자체는 폐기됐다. 최종 구현 상태는
> `README.md`와 `DECISIONS.md`를 따른다.
> 브라우저 수동 검증은 미실시(샌드박스에 Chromium 실행에 필요한 시스템 라이브러리 없음) — 사용자가 직접
> `npm run dev`로 확인.

## Slice 3 — 방향성 AgentEdge (완료: 2026-08-04)

작업:

- `AgentEdge.tsx`를 추가한다.
- 화살표는 실행 방향을, 조건 edge 라벨은 `sourceHandle`을 표시한다.
- loop는 곡률과 화살표로 구분한다. rendering data는 Canvas projection에서만 만든다.

수용 기준:

- edge ID·source/target·handle은 변경하지 않는다.
- conditional branch와 역방향 loop가 명확하게 읽힌다.
- renderer 메타데이터가 Architecture JSON에 남지 않는다.

## Slice 4 — 순수 방사형 layout (완료: 2026-08-04)

작업:

- `radialLayout.ts`에 BFS 기반 순수 함수를 만든다.
- 선택 노드를 중심으로, 무방향 인접 관계의 depth별 ring에 배치한다.
- store에는 일괄 좌표 적용과 한 번의 Undo만 추가한다.

수용 기준:

- 동일 입력은 동일 좌표를 반환한다.
- 직접 연결 node는 첫 ring, disconnected node도 누락 없이 외곽에 놓인다.
- 적용 후 position 외 topology/config/handle은 완전히 같다.

## Slice 5 — Canvas 통합과 viewport 안정화 (완료: 2026-08-04)

작업:

- 명시적 `Arrange radially` control을 추가한다.
- ResizeObserver가 panel resize마다 `fitView()`를 강제하지 않도록 제한한다.
- layout 완료 후에만 viewport를 맞춘다.

수용 기준:

- Inspector/Log panel 크기 변화가 사용자의 pan/zoom을 초기화하지 않는다.
- Arrange 시 선택 노드가 center가 되고 모든 node가 viewport에 들어온다.

## Slice 6 — 전환과 품질 검증 (구현 완료, 수동 검증 대기)

작업:

- agent mode를 feature toggle로 한 릴리스 병행한다.
- 안정화 후 `starterArchitecture.ts`의 좌표를 방사형으로 바꾼다.
- 20개 이상 node의 렌더 성능·키보드 접근성·브라우저 확대를 확인한다.

## 검증 명령

프론트 변경 후:

```bash
cd /home/licodev/projects/agentforge/ui && npm run lint && npm run build && npm run test
```

백엔드 계약을 건드린 경우:

```bash
cd /home/licodev/projects/agentforge/server && ruff check . && ruff format . && pytest
```

## 비범위

- 실제 Coordinator, Tool, Memory, Subagent runtime의 신규 도입
- resource/reference용 별도 edge 계약
- 저장 Architecture schema migration
- 자동 지속 재배치
