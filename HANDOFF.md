# Work Handoff

> Incoming agent: read the repository instructions and inspect the current worktree before acting. Repository state and fresh command output override this document if they differ.

## Snapshot

- **Updated:** 2026-08-05T18:18:50Z
- **Status:** in-progress
- **Repository:** AgentForge
- **Branch / commit:** `main` / `c0ca00e` (`Document loop control UI implementation`)
- **Worktree:** Loop Control UI work is committed. Unrelated changes remain: modified `start.sh`; untracked `.agents/`, `.opencode/`, and `agentforge`. Do not stage, revert, or delete them without user direction.

## Objective

Agent Canvas에서 모든 원래 노드와 정방향 흐름을 유지하면서, 루프를 깔끔한 `Loop Anchor`와 Loops panel/Lens로 탐색·설정할 수 있게 만든다.

완료 기준은 다음과 같다.

- Candidate와 실행 가능한 `LoopPolicy`가 데이터 모델과 UI에서 구분된다.
- 캔버스는 노드를 숨기거나 긴 feedback 선으로 혼잡해지지 않는다.
- LoopPolicy가 반복·예산·stuck·탈출 처리를 실제 compiler와 runtime event에 적용한다.
- UI가 실제 runtime event로 iteration, budget, exit reason을 표시한다.

## Current State

- 첫 Canvas UI 단계는 구현·커밋됐다. Agent Canvas는 실제 노드를 유지하고, `refine`/`retry`/`revise`/`rework`/`reject` source handle을 가진 return edge만 숨긴 뒤 source `↻ L1`, target `L1 ↩` Anchor로 대체한다.
- `findLoopCandidates()`의 SCC/simple-cycle 결과는 **Candidate**일 뿐, Architecture나 실행 routing을 바꾸지 않는다.
- 우측 상단 `Loops N` 목록에서 Candidate를 선택하면 Inspector가 read-only Candidate Lens와 감지 transition을 보여 준다.
- iteration, token/cost/time, stuck, exit reason은 아직 표시하지 않는다. LoopPolicy/runtime event 계약이 없으므로 값을 추정하지 않는다.
- 자동 LoopScope container projection과 Tier 3 outer lane은 기본 Canvas/Inspector 경로에서 제거됐다. 관련 legacy 파일은 아직 저장소에 남아 있지만 현재 기본 UI에서 사용되지 않는다.
- 브라우저 수동 시각 검증은 **Not run**이다. 이 환경은 이전에 Chromium 실행에 필요한 시스템 라이브러리가 없어 검증하지 못했다.

## Decisions and Rationale

| Decision | Rationale | Alternatives / consequences |
| --- | --- | --- |
| Canvas는 원래 노드와 정방향 edge를 항상 보존한다. | 자동 Scope 축소가 starter graph의 Reasoning/Review를 숨겨 실행 흐름 파악을 방해했다. | Legacy `LoopScopeNode` 자동 축소는 기본 동작으로 쓰지 않는다. |
| cycle detection은 Candidate만 만든다. | SCC만으로 retry/feedback/exit의 실행 의미를 안전하게 결정할 수 없다. | Candidate에서 명시적 `LoopPolicy`를 생성하는 후속 단계를 구현해야 한다. |
| feedback 관계는 짝 Anchor로 보여 주고, 전체 경로는 Lens에서 설명한다. | 긴 curved return edge를 기본 캔버스에서 없애 흐름을 읽기 쉽게 한다. | semantic source handle이 없는 cycle edge는 임의로 숨기지 않는다. |
| runtime 숫자는 event가 오기 전에는 표시하지 않는다. | node call count로 iteration/budget을 추정하면 실행 의미가 틀릴 수 있다. | backend event와 Zod 계약을 함께 추가해야 한다. |

## Completed Work

- `ui/src/canvas/Canvas.tsx` (`Canvas`) — legacy projection/lane 렌더 경로를 제거하고 Candidate annotation, return-edge filtering, Loops panel을 연결.
- `ui/src/canvas/loops/loopAnchors.ts` (`buildLoopCandidateViews`, `buildLoopAnchorsByNodeId`) — 안정된 `L1` label, Candidate ID, semantic return edge 선택을 제공.
- `ui/src/canvas/nodes/LoopAnchor.tsx` — 노드 rim의 source/re-entry Anchor, click/focus/hover endpoint pairing, screen-reader label 구현.
- `ui/src/canvas/LoopControlPanel.tsx` — `Loops N` Candidate 목록 구현.
- `ui/src/panels/LoopCandidateInspector.tsx` — Candidate status, read-only Lens, 감지 transition 표시.
- `ui/src/canvas/nodes/AgentNode.tsx` / `ui/src/panels/Inspector.tsx` / `ui/src/stores/useUiStore.ts` — Anchor 렌더, Inspector selection, transient hover 상태 연결.
- `ui/src/__tests__/loopAnchors.test.ts` — stable label, source/re-entry pairing, semantic return edge 필터를 검증.
- `work/radial-agent-canvas/LOOP_CONTROL_UX_PLAN.md` — 최신 UX 계획.
- `work/radial-agent-canvas/LOOP_CONTROL_IMPLEMENTATION.md` — 현재 구현의 행동·legacy 경계·다음 단계 정리.
- Relevant commits: `979a621`, `afef54a`, `8e3948c`, `c0ca00e`.

## Evidence and Verification

| Command or evidence | Result | Notes |
| --- | --- | --- |
| `npm run lint` in `ui/` | Passed with 3 pre-existing warnings | `TransportContext.tsx`, `NodeLibrary.tsx`, `RegistryContext.tsx`; new loop code warning 없음. |
| `npm run build` in `ui/` | Passed | `tsc -b` and Vite build passed; existing >500 kB chunk warning remains. |
| `npm run test` in `ui/` | Passed | 19 files, 91 tests passed (2026-08-05). |
| `server/.venv/bin/python -m pytest` in `server/` | Passed at prior checkpoint | 88 tests passed. Direct `server/.venv/bin/pytest` has stale `agentforce` shebang, so use `python -m pytest`. |
| Browser/manual visual verification | Not run | Current environment lacks a working Chromium runtime. |

## Remaining Work

1. Start by reading `work/radial-agent-canvas/LOOP_CONTROL_UX_PLAN.md` and inspect `server/graphs/compile.py`, `server/events.py`, `ui/src/types/events.ts`, and Architecture types to design the explicit `LoopPolicy` persistence/migration contract. Use CodeGraph first because `.codegraph/` exists.
2. Implement `LoopPolicy` in the Architecture schema and migration strategy. Preserve policy-less existing graphs as Candidates without execution changes.
3. Add per-loop state counter, guard checks (iterations, token/cost/time, stuck), and `onExhaustion` routing to the LangGraph compiler. Add mocked backend tests.
4. Extend WebSocket/Pydantic/Zod event contracts with camelCase `loopPolicyId`, iteration, usage, progress, and exit reason; update event reducer/UI together.
5. Upgrade Candidate Lens into configured-policy settings and runtime UI. Then implement Anchor overflow (`+N`) and zoom simplification.
6. Decide whether to delete legacy `LoopScopeNode`, scope projection, lane, and their tests, or retain them as an explicit Debug-only feature. Do not restore them as the default view.
7. Run visual/manual verification in a browser when a working runtime is available.

## Blockers and Open Questions

- **LoopPolicy schema/routing semantics:** no persisted contract exists. The next agent must design it before frontend settings can be functional; use the UX plan and engineering research as constraints.
- **Generic return-edge detection:** current UI hides only known semantic handles. Unknown cycles remain visible to avoid incorrect routing assumptions. Explicit policy feedback edges should replace this heuristic.
- **Manual visual verification:** blocked by unavailable browser runtime in this environment, not by a known code failure.
- **Legacy code disposition:** Debug-only retention versus deletion is undecided; current default behavior is already isolated from it.

## Working Context

- **Key files / symbols:** `ui/src/canvas/Canvas.tsx:Canvas`; `ui/src/canvas/loops/loopAnchors.ts:buildLoopCandidateViews`; `ui/src/canvas/nodes/LoopAnchor.tsx:LoopAnchor`; `ui/src/canvas/LoopControlPanel.tsx:LoopControlPanel`; `ui/src/panels/LoopCandidateInspector.tsx:LoopCandidateInspector`; `server/graphs/compile.py:compile_graph`; `server/events.py:to_frontend`.
- **Requirements / instructions:** read `AGENTS.md` and `CLAUDE.md`; if changing frontend, run `npm run lint`, `npm run build`, `npm run test`; if changing backend, run `ruff check .`, `ruff format .`, and `server/.venv/bin/python -m pytest`. Backend/frontend fields and WebSocket payloads must use camelCase and update Pydantic/Zod together.
- **Environment / setup:** project root is this directory; frontend dependencies are in `ui/node_modules`; backend virtualenv's `pytest` executable has a broken shebang, so invoke its Python module form. Required API key names are documented in `CLAUDE.md`; do not record values.
- **Scope guardrails / non-goals:** do not change user-owned `start.sh`, `.agents/`, `.opencode/`, or `agentforge`. Do not infer a LoopPolicy from SCC alone. Do not hide original nodes or make the old scope container/outer lane the default UI. ReAct internal loops remain inside AgentNode rather than external canvas policies.

## Resume Instructions

1. Read `AGENTS.md`, `CLAUDE.md`, `HANDOFF.md`, and the Loop Control documents under `work/radial-agent-canvas/`.
2. Reconcile this snapshot with `git status --short`, recent commits, and source. Current files and fresh test output override this document.
3. Start with: inspect `server/graphs/compile.py` and current Architecture/event schemas through CodeGraph, then draft the minimal persisted `LoopPolicy` contract before coding.
4. After material progress, update this handoff with fresh evidence.
