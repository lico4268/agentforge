# Loop Guard — `escalate` 소진 시그널

- **작성일**: 2026-08-11
- **상태**: 설계 승인됨 — 구현 계획(writing-plans) 대기
- **작업 스트림**: `docs/superpowers/specs/2026-08-07-loop-node-design.md`(`loop.guard` 1급 노드) 후속. `HANDOFF.md` Remaining Work item 1의 절반("`onExhaustion: 'escalate'`가 `'exit'`와 행동상 동일함")을 다룬다.
- **관련 문서**: `docs/superpowers/specs/2026-08-07-loop-node-design.md` §7·§8, `docs/superpowers/specs/2026-08-06-loop-policy-design.md`(대체됨, 참고용) 117줄

## 배경

`loop.guard` 노드의 `onExhaustion`은 `exit`/`escalate`/`fail` 세 값을 갖는다. 8/6 sidecar 설계 117줄이 이미 명시했듯, `exit`와 `escalate`는 v1에서 **라우팅이 의도적으로 동일**하다("의미상 구분은 UI 표시용, v1 라우팅 메커니즘은 동일"). 8/7 재설계도 이 결정을 그대로 계승했다(§7).

그런데 실제로 계승된 건 라우팅 동일성뿐이고, "의미상 구분"을 실어 나를 시그널 자체가 구현되지 않았다: `LoopRuntimeSchema.exitReason`에 `'escalated'` 값이 예약돼 있지만(`ui/src/types/events.ts:62-69` 주석이 이미 "reachable하지 않다"고 명시), `_make_loop_guard_node`(`server/graphs/compile.py:447-478`)는 `on_exhaustion` 값과 무관하게 항상 `evaluate_loop_guard`가 반환한 원인(`maxIterations`/`budget`/`stuck`)만 `exitReason`에 싣는다. 결과적으로 캔버스에서 `escalate`를 선택해도 이벤트 로그·워크스페이스 어디에도 `exit`와 구별되는 흔적이 없다.

## 결정: 원인 보존 + `escalated` 플래그

`exitReason`을 `'escalated'`로 덮어쓰는 대안(트립 원인 손실)과 실제 라우팅을 분기하는 대안(v1이 명시적으로 배제한 범위, 캔버스 배선까지 건드리는 큰 작업)을 검토했다. 채택한 안은 별도 `escalated: boolean` 필드를 추가해 "왜 멈췄나"(`exitReason`, 그대로 유지)와 "그래서 사람이 봐야 하나"(`escalated`)를 직교 축으로 유지하는 것이다. 원인 정보를 잃지 않고, 나중에 실제 라우팅 분기를 얹더라도 이 플래그와 자연스럽게 합성된다.

## 변경 사항

1. `server/graphs/compile.py`의 `_make_loop_guard_node` — 가드가 트립됐고(`should_continue=False`) `on_exhaustion == "escalate"`일 때만 `loop_runtime_event["escalated"] = True`를 추가한다. `exitReason`은 지금처럼 `evaluate_loop_guard`가 반환한 원인을 그대로 유지한다. `exit`/`fail`일 땐 `escalated` 키 자체를 넣지 않는다(다른 optional 필드들과 동일한 관례).
2. `ui/src/types/events.ts`의 `LoopRuntimeSchema`에 `escalated: z.boolean().optional()`을 추가한다.
3. 백엔드 `ExecutionEvent.loop_runtime`은 검증 없는 raw `dict`(`server/events.py`)라 별도 스키마 변경이 불필요하다.

## 범위 밖

- **kind-specific 가드 프리셋** — Remaining Work item 1의 나머지 절반이지만, v1 scope guardrail(`HANDOFF.md` Working Context)이 이미 out-of-scope로 명시했다. 이번 설계와 무관하게 그대로 유지.
- **UI 시각화** — `LogPanel`/`Inspector` 어디도 현재 `loopRuntime` 필드를 전혀 렌더링하지 않는다(그렙으로 확인, `ui/src/types/events.ts:101` 타입 선언 외 소비처 없음). `escalated`를 화면에 다르게 그리는 작업은 `HANDOFF.md` Remaining Work item 3("Loop Control UI 설정 화면 폴리시")의 몫으로 남긴다 — 이번 설계는 이벤트에 신호를 싣는 데까지다.
- **실제 라우팅 분기** — 8/6·8/7 설계가 v1에서 명시적으로 배제한 범위. 이번 결정으로도 뒤집지 않는다.

## 테스트 계획

- `server/tests/test_compile.py`: `onExhaustion: "escalate"` + `maxIterations` 트립 시나리오를 새로 추가 — `escalated is True`이면서 `exitReason == "maxIterations"`(원인 보존 확인), 최종 라우팅은 여전히 `exit` 포트 타깃(라우팅 불변 확인).
- 기존 `onExhaustion: "exit"` 트립 테스트(`test_loop_guard_max_iterations_trips_to_the_exit_port` 등)에 `"escalated" not in loop_runtime`류 부재 단언을 추가해 회귀를 잡는다.
- 프론트: `escalated`는 검증 없는 optional 필드라 신규 테스트는 불필요 — 기존 `loopGuardManifest.test.tsx`/이벤트 스키마 테스트가 그대로 통과하는지만 확인한다.

## 완료 기준

- [ ] `compile.py`에 `escalated` 플래그 추가 + 신규/회귀 테스트 통과
- [ ] `events.ts`의 `LoopRuntimeSchema`에 `escalated` optional 필드 추가
- [ ] 백엔드(`pytest`, `ruff check`, `ruff format`)·프론트(`npm run test`, `npm run build`) 전체 통과
- [ ] `HANDOFF.md`/`ROADMAP.md`에 Remaining Work item 1의 절반(escalate 시그널)이 완료됐음을 기록, 나머지 절반(kind-specific 프리셋)은 여전히 out-of-scope로 남아 있음을 명시
