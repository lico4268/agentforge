# Loop Control UI 1차 구현 정리

## 목적

기존 Loop Scope 컨테이너 자동 축소와 outer lane은 원래 노드를 숨기거나 피드백 선을 길게 휘게 만들어, 일반 실행 흐름을 읽기 어렵게 했다. 이번 구현은 모든 원래 노드를 유지한 채 루프 관계를 작은 `Loop Anchor`로 보이게 하는 첫 단계다.

## 사용자 화면 동작

```text
Reasoning ──────────────────→ Review
  [ L1 ↩ ]                     [ ↻ L1 ]
  re-entry target              feedback source
```

- Agent Canvas는 모든 원래 노드와 정방향 edge를 그대로 렌더한다.
- `refine`, `retry`, `revise`, `rework`, `reject`처럼 return 의미가 확인된 edge는 기본 Canvas에서 숨긴다.
- 숨긴 edge의 source에는 `↻ L1`, target에는 `L1 ↩` 마커를 노드 rim 바깥에 표시한다.
- 마커를 hover하거나 keyboard focus하면 같은 `L1`의 양쪽 마커와 관련 노드 테두리를 강조한다.
- 마커 클릭 또는 Enter/Space는 해당 Candidate를 선택하고 Inspector를 연다.
- 우측 상단 `Loops N`을 열면 감지된 루프 후보 목록을 확인하고 선택할 수 있다.

## Candidate와 정책의 구분

현재 화면의 루프는 **Candidate**다.

- `findLoopCandidates()`가 SCC/단순 cycle을 찾아 후보를 만든다.
- `loopAnchors.ts`가 후보에 안정된 `L1`, `L2` 식별자와 Anchor 위치를 부여한다.
- Candidate는 실행 설정을 저장하거나 routing을 변경하지 않는다.
- Inspector의 Candidate Lens는 노드와 감지된 transition을 국소적으로 보여 주지만, iteration·비용·시간 같은 값을 추정하지 않는다.

실행 가능한 `LoopPolicy`와 runtime event는 아직 구현하지 않았다. 따라서 Inspector에는 policy가 아직 없다는 사실과 다음 계약에 필요한 설정 항목만 표시한다.

## 구현 파일

| 파일 | 역할 |
| --- | --- |
| `ui/src/canvas/loops/loopAnchors.ts` | Candidate ID/label, semantic return edge, node별 Anchor 계산 |
| `ui/src/canvas/nodes/LoopAnchor.tsx` | rim 고정 Anchor, click/focus/hover interaction, 접근성 이름 |
| `ui/src/canvas/nodes/AgentNode.tsx` | Anchor를 노드에 렌더하고 선택/hover loop 강조 |
| `ui/src/canvas/LoopControlPanel.tsx` | `Loops N` Candidate 목록과 선택 UI |
| `ui/src/panels/LoopCandidateInspector.tsx` | Candidate 상태, Loop Lens, 감지 transition 표시 |
| `ui/src/canvas/Canvas.tsx` | legacy projection/lane 제거, Candidate annotation과 edge filtering 연결 |
| `ui/src/panels/Inspector.tsx` | `loop:*` 선택 시 Candidate Inspector 연결 |
| `ui/src/stores/useUiStore.ts` | Anchor endpoint pairing을 위한 일시 hover 상태 |

## legacy 처리

`LoopScopeNode`, `loopScopeProjection`, `tier3LoopLane` 등 기존 파일은 이 커밋에서 삭제하지 않았다. 기본 Canvas 렌더 경로와 Inspector는 더 이상 사용하지 않으며, 향후 Debug 전용으로 남길지 제거할지는 LoopPolicy 구현 이후 결정한다.

기존 `rawExecutionView`/scope expansion UI state도 같은 이유로 남아 있지만, 현재 기본 화면에는 관련 토글이나 projection이 없다.

## 검증

- `npm run lint`: 통과 (기존 경고 3건만 유지)
- `npm run build`: 통과
- `npm run test`: 19개 파일, 91개 테스트 통과
- 신규 `loopAnchors.test.ts`: stable `L1`, source/re-entry pairing, semantic return edge만 숨기는 동작 검증

## 다음 단계

1. `LoopPolicy`를 Architecture에 저장할 타입·migration·UI 생성 흐름을 설계한다.
2. server compiler에 per-loop counter, guard, exit/exhaustion routing을 구현한다.
3. WebSocket event에 `loopPolicyId`, iteration, token/cost/time, progress, exit reason을 추가한다.
4. Candidate Inspector를 실제 policy settings와 runtime Lens로 확장한다.
5. 다중 Anchor overflow(`+N`)와 줌 축소 표현을 구현한다.
