# Radial Agent Canvas Worklog

AgentForge 캔버스를 수직 파이프라인 편집기에서 방사형 실행 맵으로 전환하는 작업 기록이다.

## 운영 방식

- 구현 전: `PLAN.md`에 slice·수용 기준을 기록한다.
- 구현 중: 이 폴더에 해당 slice의 설계 결정과 검증 결과를 추가한다.
- 구현 후: 변경 파일, 실행한 검사, 결과와 남은 위험을 기록한다.
- 실행 계약(`Architecture`, edge handle, `compile_graph`)을 바꾸는 일은 별도 결정으로 명시한다.
- OpenRouter coding agent는 읽기 전용 점검을 최대 8 rounds, 쓰기 작업을 최대 14 rounds로 제한한다. 결과가 없거나 `Stopped after maximum tool rounds`가 나오면 즉시 중단·기록하고, 같은 모델로 반복 재시도하지 않는다.

## 현재 상태

- 방사형 canvas, 포트 가시성, cycle candidate 탐지까지는 구현돼 있다.
- 자동 `LoopScope` 축소/컨테이너, Tier 3 outer lane은 이전 실험 구현이다. 새 기본 UX에서는 사용하지 않으며, 원래 노드와 정방향 edge를 항상 보존한다.
- 현재 활성 계획은 `LOOP_CONTROL_UX_PLAN.md`다. Loop Anchor, Loops panel, Loop Lens, 명시적 LoopPolicy 계약 순으로 재구성한다.
- 기존 구현의 자동 축소를 새 계획에 맞춰 격리한 뒤, policy/runtime 계약을 별도 작업으로 진행한다.
- 기준선: 현재 수직 카드형 `GenericNode`와 상/하 port
- 완료 범위: Slice 0 — 계약 고정 및 기준선 검증
- 완료 범위: Slice 1 — classic/agent 이중 renderer와 Inspector checkpoint 액션
- 완료 범위: Slice 2 — 원형 AgentNode와 원주형 port
- 완료 범위: Slice 3 — 방향성 AgentEdge
- 완료 범위: Slice 4 — 명시적 방사형 layout과 Undo
- 완료 범위: Slice 5 — viewport 안정화와 interaction 검증
- 완료 범위: Slice 6 — agent mode 기본 전환과 starter graph 방사형 좌표
- 보류 범위: Slice 6 — 실제 브라우저 drag/connect/focus 수동 검증

## 문서 목록

- `PLAN.md`: 단계별 구현 계획과 수용 기준
- `LOOP_CONTROL_UX_PLAN.md`: 현재 루프 UX의 단일 계획 — Loop Anchor, Loops panel, Loop Lens, LoopPolicy
- `LOOP_ENGINEERING_RESEARCH.md`: 루프 제어·runtime 설계의 조사 자료 (시각 UI 제안은 최신 계획을 우선한다)
- `DECISIONS.md`: 제품/기술 결정 및 결정 대기 항목
