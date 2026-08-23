# Loop 재진입 마커 — synthetic 오버레이 대신 진짜 노드

- **작성일**: 2026-08-22
- **상태**: 설계
- **관련 문서**: `docs/superpowers/specs/2026-08-07-loop-node-design.md` (`loop.guard`를 1급 노드로 만든 원 설계 — 이 문서가 확립한 "루프 제어는 sidecar가 아니라 캔버스에 그려진 노드"라는 원칙을 이번에도 그대로 계승·확장)

## 배경

이번 세션에서 drilled-in 루프 뷰에 "도돌이표"처럼 시작/끝을 표시하는 기능을 만들었다. 처음에는 반원(half-capsule) 모양의 synthetic 마커(`LoopBoundaryNode.tsx` + `loopProjection.ts`의 `projectDrilledInView`가 매 렌더마다 주입하는 `__loopBoundary__` 타입 노드)로 구현했고, 이후 실제 노드와 같은 112px 원형으로 바꿨다. 하지만 이 마커는 처음부터 끝까지 **view-layer에만 존재하는 가짜 노드**였다 — `useGraphStore`에 없고, `toArchitecture()`로 저장되지 않고, 드래그도 실제 연결도 안 됐다.

사용자 피드백: "이 노드들도 사용자가 마음대로 일반 노드들처럼 붙일 수 있도록 해야지 왜 특수 노드로 만드는거야." — synthetic 오버레이가 아니라 진짜 그래프 노드로 승격해야 한다는 것. 조사 결과 `server/graphs/compile.py`에 이미 `PASSTHROUGH_TYPES`(`io.input`/`io.output`/`model.binding`)라는, "로직 없이 그냥 통과시키는 노드" 매커니즘이 있어 이 승격 비용이 매우 낮다는 것을 확인했다.

## 목표 / 비목표

**목표**
- 루프의 재진입 지점을 사용자가 캔버스에 직접 배치·이동·재배선할 수 있는 진짜 노드(`loop.reentry`)로 표현한다.
- 이 노드는 Architecture에 저장되고, 백엔드 `compile_graph`가 실제로 해석하며, 다른 노드와 동일하게 자유롭게 연결 가능하다.
- `loop.guard`는 무변경 — 이미 진짜 노드이고 이미 루프의 "끝"(재진입/탈출을 결정하는 지점) 역할을 하므로, 대응하는 "End" 노드 타입은 만들지 않는다.
- 배치는 선택 사항이다 — `loop.guard`의 `loopBack`이 이 노드를 거치지 않고 바로 루프 본문 노드를 가리켜도 지금처럼 유효하다(§4 "가드 없는 cycle → 컴파일 에러" 검증과 무관, 그 검증은 그대로 유지).

**비목표**
- `loop.guard`를 "End" 타입으로 개명하거나 재구성하지 않는다 — 이미 실제 노드이므로 얻는 게 없고 기존 그래프/테스트/문서 전반의 `loop.guard` 참조를 깨는 비용만 크다.
- synthetic 마커를 "실제 노드로 승격하는 인터랙션"(드래그하면 실체화) 같은 건 만들지 않는다 — 사용자가 노드 라이브러리에서 직접 꺼내 놓는 일반적인 캔버스 조작으로 충분하다.
- 루프 시작 위치를 강제하지 않는다 — 배치 안 하면 그냥 지금처럼 보인다(가드+멤버만, 북마크 노드 없음).

## 채택한 접근

`loop.reentry`라는 새 1급 노드 타입 하나만 추가하고, 이번 세션에 만든 synthetic 마커 시스템 전체(`LoopBoundaryNode.tsx`, `loopProjection.ts`의 boundary 주입 로직)를 삭제한다.

다른 대안을 검토했으나 기각:

| 접근 | 설명 | 기각 사유 |
| --- | --- | --- |
| A. `loop.reentry` 단일 노드 추가 (채택) | 통과 노드 1개만 신설, `loop.guard`는 무변경 | 백엔드/프론트 변경 최소, 기존 원칙과 정합 |
| B. `loop.start`+`loop.end` 두 노드, `loop.guard` 설정을 `loop.end`로 흡수 | Start/End 대칭 완성 | `loop.guard`가 이미 실제 노드라 실익 없이 전체 개명 비용만 큼 |
| C. synthetic 마커를 유지하되 드래그 시 실체 노드로 "승격"하는 인터랙션 | 지금 UX 유지하면서 필요시 실체화 | 두 가지 노드 표현(투영/실체)을 오가는 상태 기계가 필요해 복잡도만 늘고, 사용자가 요청한 건 애초에 "그냥 일반 노드로"였음 |

## 설계

### 1. 노드 계약 — `loop.reentry` manifest

`server/manifests.py`의 `BUILTIN_MANIFESTS`에 추가:

```python
{
    "type": "loop.reentry",
    "runtime": "passthrough",
    "category": "policy",
    "label": "Loop Start",
    "description": "루프가 다시 도는 지점을 표시하는 시각 마커. 로직 없이 입력을 그대로 통과시킨다 — loop.guard의 loopBack 포트를 여기로 연결.",
    "inputs": [{"id": "in", "label": "In", "dataType": "any", "required": True}],
    "outputs": [{"id": "out", "label": "Out", "dataType": "any"}],
    "config": [],
},
```

`category: "policy"`를 재사용해 `loop.guard`/`review.intent`와 같은 그룹으로 노드 라이브러리에 묶인다. 온캔버스 아이콘은 `AgentNode`가 `CATEGORY_META[category].icon`(policy 방패 아이콘)을 그대로 쓴다 — 카테고리별 고정 아이콘 체계는 이번 설계 범위 밖이라 손대지 않는다. 대신 `ui/src/lib/categoryStyle.ts`의 `NODE_TYPE_ICONS`(노드 라이브러리 패널 전용 아이콘 맵)에 `'loop.reentry': 'restart_alt'`를 추가해 라이브러리에서는 구분 가능하게 한다.

`ui/src/types/manifest.ts`의 `RUNTIMES` 튜플에 `'passthrough'` 추가 (`io.input`/`io.output`의 `'io'`, `model.binding`의 `'model'`과 별개로, 이번에 신설).

### 2. 컴파일러 배선 — `PASSTHROUGH_TYPES`에 한 줄 추가

`server/graphs/compile.py:52`:

```python
PASSTHROUGH_TYPES = {"io.input", "io.output", "model.binding", "loop.reentry"}
```

`_make_passthrough_node`는 `node_type`이 `"io.input"`/`"io.output"`이 아닌 모든 타입에 대해 이미 `output=None, updates={}`인 순수 통과 동작을 한다(`model.binding`이 오늘도 이 경로를 탄다) — `loop.reentry` 전용 분기는 필요 없다.

일반 엣지 배선(`_build_plain_edge_plan`, §701-721)과 루프 멤버 유도(`_derive_loop_members`, §3d)는 노드 타입을 가리지 않고 그래프 도달성만 본다 — `loop.reentry`가 `loop.guard`의 `loopBack`과 실제 루프 본문 사이에 끼어 있어도 별도 처리 없이 자동으로 배선되고 멤버로 잡힌다. `human.checkpoint`/`loop.guard`/`review.intent`만 예외 처리하는 두 번째 루프(§710-713)도 무변경 — `loop.reentry`는 그 예외 목록에 없으므로 정상적으로 plain edge 대상이 된다.

### 3. Synthetic 마커 시스템 삭제

이번 세션 중 추가된 다음을 전부 삭제한다:

- `ui/src/canvas/nodes/LoopBoundaryNode.tsx` (파일 전체 삭제)
- `ui/src/canvas/loop/loopProjection.ts`: `LOOP_BOUNDARY_NODE_TYPE`, `LoopBoundaryRole`, `LoopBoundaryNodeData`, `BOUNDARY_GAP`/`BOUNDARY_SIZE` 상수, `loopBoundaryNode()` 함수, `projectDrilledInView`의 `boundaryNodes` 주입 로직 — `projectDrilledInView`는 다시 "가드 + 멤버 + 그 사이 엣지"만 반환하는 원래 형태로 돌아간다. **`isLoopBackEdge` 기반 loopBack 엣지 필터링도 함께 제거한다** — "연결선을 그리지 않는다"는 원칙은 synthetic 마커(가짜 노드끼리의 가짜 페어링)에만 해당했던 것이고, `loop.reentry`는 진짜 노드이므로 `loop.guard → loop.reentry` 엣지도 다른 모든 엣지와 동일하게 평범한 실선으로 그려야 "진짜 연결 가능한 노드"라는 목표에 맞다. 그 결과 `isLoopBackEdge`(`ui/src/canvas/edges/edgePresentation.ts`)를 호출하는 곳이 없어지므로 함수와 대응 테스트(`edgePresentation.test.ts`)도 함께 삭제한다.
- `ui/src/canvas/Canvas.tsx`: `LoopBoundaryNode` import, `LOOP_BOUNDARY_NODE_TYPE` import·`nodeTypes` 등록 제거.
- `ui/src/__tests__/loopProjection.test.ts`: boundary 마커 관련 3개 테스트(위치·no-op 케이스) 삭제, "shows only the guard and its members" 테스트는 `e9`(loopBack)이 여전히 필터링되는지만 검증하도록 조정.

`deriveLoopMembers.ts`의 `findLoopBackTarget`는 `deriveLoopMembers` 자체가 여전히 쓰므로 무변경.

### 4. 스타터 그래프 업데이트

`ui/src/app/starterArchitecture.ts`에 `loop.reentry` 노드를 하나 추가해 새 타입을 기본 그래프에서 바로 시연한다:

```
loop_guard --loopBack--> reentry --out--> reasoning   (기존 e9를 대체)
```

- 새 노드: `{ id: 'loop_reentry', type: 'loop.reentry', position: { x: 220, y: 380 }, config: {} }` — reasoning(x:472) 왼쪽, review/loop_guard와 같은 y=380 줄에 놓아 시각적으로 루프의 "시작"이 왼쪽 끝에 오도록 배치.
- `e9`(`loop_guard --loopBack--> reasoning`)를 `loop_guard --loopBack--> loop_reentry`로, 새 엣지 `loop_reentry --out--> reasoning`을 추가.
- `reasoning`의 다른 입력(`e2`: planning→reasoning, `e3`: input→reasoning)은 무변경.

### 5. 테스트 계획

- **백엔드** (`server/tests/test_compile.py`): `loop.reentry`를 낀 루프가 정상 컴파일·실행되는지(전달만 하고 state를 안 바꾸는지), `_derive_loop_members`가 이 노드를 멤버로 포함하는지 확인하는 케이스 추가.
- **프론트** (`ui/src/__tests__/`): `starterArchitecture.test.ts`가 새 노드/엣지 형태를 반영하도록 갱신. `loopProjection.test.ts`는 §3의 삭제 반영 + `loop.reentry`가 낀 그래프에서 drilled-in 뷰가 그 노드를 평범한 멤버로 포함하는지(마커 아님, `visible` 집합의 일반 노드) 검증하는 케이스 추가.
- 최종 확인은 `npm run test`(vitest) + `npm run build`(`tsc -b` 포함, 리포 컨벤션상 test 통과가 build 통과를 보장하지 않음) 양쪽 다.

## 알려진 후속 작업

- 온캔버스 아이콘이 `review.intent`/`loop.guard`와 같은 policy 방패 아이콘을 공유해 셋을 캔버스에서 구분하려면 라벨 텍스트("Loop Start")에 의존해야 한다 — 카테고리 단위가 아니라 노드 타입 단위로 아이콘을 오버라이드하는 건 `AgentNode.tsx` 전체에 영향을 주는 더 큰 변경이라 이번 범위 밖으로 남긴다.
- `loop.reentry`가 여러 개 배선되거나(같은 loopBack이 여러 노드를 가리킴은 오늘도 불가 — `_handle_targets`가 handle당 target 1개), 루프 밖에서 참조되는 등의 오배선 케이스에 대한 컴파일 에러 메시지는 기존 `loop.guard` 검증(§9)을 그대로 우회하지 않는지만 테스트로 확인하고, 별도 신규 검증은 추가하지 않는다(passthrough 노드로서 오배선은 이미 `_build_plain_edge_plan`/entry-node 검증이 잡는다).
