> 📚 **낡은 설계** — [DIRECTION.md](../../../DIRECTION.md)로 대체됐다. 분기 이름·노드 역할 고정에 관한 서술은 현재 방향과 다르다. 당시 판단 근거를 찾을 때만 읽는다.

# UI 설계 철학 — 캔버스·패널 상호작용 원칙 정리 + 엣지/루프 재설계

- **작성일**: 2026-08-14
- **상태**: 설계 승인 완료, 구현 대기
- **작업 스트림**: `work/radial-agent-canvas/` (Loop Control UI) 후속
- **관련 문서**: `work/radial-agent-canvas/DECISIONS.md`, `LOOP_CONTROL_UX_PLAN.md`, `LOOP_CONTROL_IMPLEMENTATION.md`, `docs/superpowers/specs/2026-08-07-loop-node-design.md`
- **범위**: 캔버스(노드/엣지/포트) + 주변 패널(Toolbar/Inspector/LogPanel) 상호작용 원칙. 시각 스타일(색상 팔레트·타이포그래피 자체)은 범위 밖.

## 배경

`work/radial-agent-canvas/`에서 원형 노드·방사형 배치·포트 360도 배치·`loop.guard` 노드까지 여러 슬라이스를 거치며 방향 자체는 옳게 잡아왔지만, 그 판단들을 관통하는 원칙이 코드와 개별 결정 기록(`DECISIONS.md`)에 흩어져 있을 뿐 하나로 정리된 적이 없었다. 그 증거로, `DECISIONS.md`의 "결정 대기 #4"(checkpoint 조작 위치)는 실제로는 이미 코드에서 Inspector 중심으로 확정돼 있는데도 문서에는 여전히 "대기"로 남아 있었다.

이번 세션은 두 가지를 함께 했다: (1) 기존 코드에 이미 일관되게 존재하던 원칙을 읽어내 문서화하고, (2) 사용자가 실제 사용하며 느낀 두 가지 구체적 불편 — 엣지가 얽혀 보이는 문제, 루프 제어가 눈에 잘 안 보이는 문제 — 을 브라우저 목업으로 비교해가며 새로 결정했다.

## 목표

- 캔버스/패널이 각각 어떤 역할만 맡는지 원칙으로 고정해, 다음 기능을 추가할 때 판단 기준으로 쓸 수 있게 한다.
- 엣지가 노드 경계 앞에서 꺾여 겹쳐 보이는 현재 문제의 **근본 원인**을 코드 레벨에서 규명하고, 대안을 확정한다.
- `loop.guard` 노드는 있지만 "루프가 도는 범위"를 캔버스에서 한눈에 못 알아보는 문제를 해결한다.
- 노드의 input/output 개수·구성에 관한 UI 원칙을 정한다.
- `DECISIONS.md`를 실제 코드 상태와 이번 결정에 맞게 정합화한다.

## 비목표

- 색상 팔레트, 타이포그래피, 노드 지름(96/112/128px) 등 순수 시각 스타일 조정 — `DECISIONS.md` 결정 대기 항목으로 남겨둔다.
- `loop.guard`의 5축 guard 설정 폼 자체의 재설계 — 기존 `GenericNode`/config 패널 방식 유지.
- 중심 노드 자동 선정, classic renderer 폐기 시점 등 이번 대화에서 다루지 않은 나머지 결정 대기 항목.
- Input Slots의 백엔드 계약(manifest 스키마 확장, `compile.py` 배선, prompt 조립 방식) — 이번 문서는 UI 방향만 정하고, 실제 구현은 후속 설계로 넘긴다.

## 1. 기존 원칙 (코드에서 추출, 이번에 처음 문서화)

코드(`Inspector.tsx`, `AgentNode.tsx`, `LogPanel.tsx`, `Toolbar.tsx`, `radialPortGeometry.ts`)를 근거로 다음 원칙이 이미 일관되게 지켜지고 있었다:

1. **Canvas = 역할·관계·실행상태 지도.** 설정 편집은 캔버스에서 하지 않는다(`DECISIONS.md`: "원형 노드의 상세 정보는 Inspector에 둔다").
2. **Inspector = 선택된 대상의 유일한 상세 정보원.** config, Model Slots, Connections, Last I/O, Execution Metrics 전부 Inspector 한 곳에 모인다.
3. **점(dot)이지 패널이 아니다.** 캔버스 노드는 "결정이 필요함"을 작은 배지 하나로만 가리키고(`AgentNode.tsx`의 `isPendingCheckpoint` 점), 실제 액션(`CheckpointActions`)은 항상 Inspector에만 존재한다.
4. **Progressive disclosure.** 포트 점은 기본 숨김(`useUiStore.showConnectionPorts`), Advanced/Reliability 섹션은 `<details>` 접힘, Connections 섹션은 엣지가 있을 때만 렌더.
5. **카테고리 색이 패널을 잇는 연결 조직.** `CATEGORY_META`의 색이 Library 카드 좌측 테두리, Canvas 노드, Inspector 헤더 점에서 동일하게 재사용된다. Loop 전용 보라/인디고는 카테고리 색과 절대 섞지 않는다(`LOOP_CONTROL_UX_PLAN.md`).
6. **Inherit vs override.** `InheritNumber`: 빈 값=상속, 값을 넣으면 override, 되돌리기 아이콘으로 명시적 해제. 0과 unset을 구분한다.
7. **아직 없는 걸 있는 척하지 않는다.** 실제 backend 계약이 없는 개념(Coordinator/Tool/Memory 등)은 UI에 노출하지 않는다(`DECISIONS.md` 결정 대기 #5, 원칙 자체는 이미 확정).
8. **LogPanel = 실행 전체의 시간순 기록.** 캔버스가 지금 어떤 부분을 보여주고 있든 상관없이 항상 전체 이벤트/아티팩트를 보여준다.

## 2. 엣지 라우팅 — 직선 우선, loop-back만 곡선

### 근본 원인

`RadialNodePorts.tsx`가 각 포트를 실제 파트너 방향의 연속 각도(0~360°)에 정확히 배치하지만(`pointFromAngleDeg`), 그 각도를 곡선의 접선 방향으로 넘길 때 `positionFromAngleDeg`(`radialPortGeometry.ts:51`)가 `Position.Top/Right/Bottom/Left` 4방향으로 반올림한다. React Flow의 `getBezierPath`는 이 4방향 `Position`으로 곡선의 시작/끝 접선을 계산하므로, 점의 실제 위치와 곡선이 진입하는 방향이 대각선일수록 어긋나 노드 경계 바로 앞에서 꺾인다. 한 노드에 여러 파트너가 붙으면 이 꺾임이 겹쳐 "얽힌" 인상을 만든다 — 이것이 이번 세션에서 확인한, 사용자가 지적한 문제의 실제 코드 레벨 원인이다.

### 결정

- **정방향 엣지는 항상 직선**(노드 경계 → 노드 경계). 점의 실제 각도와 선이 항상 일치하므로 꺾임 자체가 사라진다.
- **loop-back 엣지만** 곡선 + 점선 + loop-purple(`#a78bfa` 계열)로 구분한다. 정방향 흐름과 되돌아가는 관계가 형태·색 둘 다로 구분된다.
- 부수 효과: 직선 경로는 접선 방향 계산 자체가 필요 없으므로, 4방향 quantization 문제가 정방향 엣지에서 구조적으로 사라진다. loop-back 엣지의 곡선 접선은 어차피 "눈에 띄게 휘어야" 하는 목적이라 quantization 오차가 문제되지 않는다.
- 기존 원칙 승계: 포트 점은 계속 기본 숨김, 방향은 화살표로만 전달한다(`DECISIONS.md`의 기존 결정 유지).

## 3. 루프 표현 — 접힌 노드 + 더블클릭 드릴다운

### 배경: 이미 한 번 시도했다가 되돌린 접근과의 구분, 그리고 현재 실제 상태

`LoopScopeNode`(Slice 8, `LOOP_CONTROL_IMPLEMENTATION.md`)가 루프를 캔버스 위 인라인 컨테이너 박스로 접었지만, "원래 노드를 숨기거나 흐릿하게 만들어 일반 실행 흐름을 읽기 어렵게 한다"는 이유로 되돌려졌고(`8e3948c`, `0d003b2`), 그 다음 단계로 Loop Anchor(짝 토큰) + Loop Lens(국소 다이어그램) + Loops panel 방식을 채택했었다(`LOOP_CONTROL_UX_PLAN.md`).

**그런데 그 Anchor/Lens/Panel 체계는 이후 `2026-08-07-loop-node-design.md` 설계(2026-08-08 구현·검증 완료)에서 `loop.guard`를 1급 캔버스 노드로 만들며 전부 삭제됐다** — `ui/src/canvas/loops/{loopCandidates,loopAnchors}.ts`, `LoopCandidateInspector.tsx`, `LoopAnchor.tsx`, `LoopControlPanel.tsx`가 모두 제거됐고(실측: 저장소에 `*loop*` 이름의 프론트 파일은 테스트 1개뿐), 현재 `loop.guard`는 **어떤 특수 시각화도 없이** `GenericNode`/`AgentNode`가 다른 노드와 완전히 동일하게 렌더한다(`category: "policy"` 색만 공유). 즉 이번 절에서 설계하는 "접힌 루프 노드 + 드릴다운"은 기존 무언가를 **대체하는 게 아니라, 현재 존재하지 않는 것을 새로 만드는 것**이다 — 브레인스토밍 과정에서 이 사실을 놓치고 "대체"라고 표현했던 부분을 이 문서에서 바로잡는다.

이번에 사용자가 제안한 방식은 가장 처음 시도했던 인라인 컨테이너와 표면적으로 비슷해 보이지만 구조적으로 다르다: **인라인 컨테이너는 접힌 상태가 항상 같은 캔버스 위에 남아 반쪽짜리 정보를 상시 노출**했던 반면, **더블클릭 드릴다운은 접힌 상태와 펼친 상태가 서로 다른 화면**이라 반쪽짜리 상태 자체가 존재하지 않는다. 브라우저 목업으로 두 방식을 나란히 비교해 이 차이를 확인한 뒤 드릴다운을 선택했다.

### 결정

- **메인 캔버스**: 루프는 물결 헤일로(옅어지는 동심원 2겹, loop-purple, 기존 `running` 상태 box-shadow glow와 같은 시각 언어 재사용) 원 노드 하나로 보인다.
- 접힌 상태에서도 **보통 노드와 동일하게 여러 개의 in/out 포트를 그대로 노출**한다 — 예를 들어 루프 내부의 `review.intent`가 갖는 `accept → Output`, `escalate → Human checkpoint` 같은 분기는 접힌 루프 노드의 출력 포트로도 그대로 보여야 한다. 루프를 접는 것은 **내부 노드 개수를 숨기는 것이지, 외부로 나가는 분기 구조를 숨기는 것이 아니다.**
- 코너에 펼치기 배지(멤버 수 + `open_in_full` Material Symbol). 평소엔 은은하다가 hover 시 진해진다(기존 progressive disclosure 원칙 적용).
- **더블클릭 → 화면이 그 루프의 내부 뷰로 전환**된다(같은 캔버스에 박스로 안 남음). 상단에 breadcrumb이 뜨고 클릭하면 메인 그래프로 복귀한다.
- Loop Anchor/Lens/Loops panel은 이미 삭제되어 있으므로 "대체"할 코드가 없다 — 이번 기능은 순수 신규 구현이다. Loops panel과 동등한 전역 목록 진입점이 필요한지는 이번 설계 범위에 포함하지 않는다(후속 작업 참고) — 스타터 그래프처럼 루프가 하나뿐이고 화면 안에 항상 보이는 경우에는 캔버스 위 더블클릭만으로 충분하기 때문이다.

**정체성 링 vs 상태 표현**: 물결 헤일로(바깥 2겹)는 "이 노드는 접힌 루프다"를 나타내는 고정 정체성 마커로 항상 loop-purple이다. 안쪽 원의 테두리는 기존 `AgentNode`와 동일하게 `statusColor(status, accent)`를 그대로 따른다(running/success/failed/skipped) — 즉 루프 노드는 카테고리 색 대신 loop-purple을 accent로 쓰는 것일 뿐, 상태 표현 로직 자체는 다른 노드와 동일하다. 두 신호(고정 정체성 vs 실행 중 상태)를 같은 테두리 하나로 섞지 않는다.

## 4. 드릴다운 시 패널 연동 — 기존 원칙의 확장

루프 내부 뷰로 들어가도 각 패널의 역할은 바뀌지 않는다. 이는 `DECISIONS.md`의 기존 원칙("Loop Scope는 순수 캔버스 view-layer 투영이다 — Architecture/`toArchitecture()`/LangGraph compile에는 전혀 영향 없음")을 드릴다운에도 그대로 확장 적용한 것이다.

| 패널 | 드릴다운 진입 시 동작 |
| --- | --- |
| Toolbar | 로고 자리에 breadcrumb(`Agentforge / Loop L1`)이 대신 뜨고 뒤로가기를 제공한다. Run 버튼·아키텍처/모델 선택 등 글로벌 실행 컨트롤은 그대로 유지된다 — 드릴다운은 순수 뷰 이동이지 실행 범위 변경이 아니다. |
| Inspector | 변경 없음. 어느 레벨에서 선택하든 선택된 노드의 상세를 그대로 보여준다. |
| LogPanel | 변경 없음. 실행 전체의 시간순 이벤트/아티팩트는 캔버스가 지금 어느 레벨을 보여주는지와 무관하다. |

## 5. In/Out 포트 설정 원칙

- **Output**: 별도 설정 UI가 필요 없다. 하나의 출력 값은 설정 없이 여러 노드로 fan-out될 수 있다(값 복제일 뿐). 서로 다른 종류의 출력이 필요하면 manifest가 이름 있는 별도 포트로 고정 선언한다 — 이미 `review.intent`(accept/refine/clarify), `loop.guard`(loopBack/exit)가 쓰고 있는 패턴이며 새로 만들 필요가 없다.
- **Input**: 대부분의 노드는 manifest가 고정 이름의 입력 포트를 선언하는 현행 방식을 유지한다(예: `loop.guard`의 `Feedback` 입력). 다만 **입력 개수가 가변인 노드 타입**(예: 여러 소스의 context를 합치는 노드)에 한해, 이미 있는 `ModelSlotsEditor` 패턴(추가/삭제 + role 라벨)을 Inspector에 "Input Slots"로 일반화해 적용한다. 구체적 백엔드 계약(어떤 노드 타입이 가변 입력을 갖는지, 합치는 방식)은 이번 문서의 범위 밖이며 후속 설계로 넘긴다.

## 6. `DECISIONS.md` 정합화

구현 착수 시 다음을 `work/radial-agent-canvas/DECISIONS.md`에 반영한다:

- 결정 대기 **#4(checkpoint 조작 위치)** → 이미 코드에서 Inspector 중심으로 확정돼 있으므로 "확정" 표로 이동.
- 이번 세션 결정 4건(엣지 라우팅 직선+loop-back 곡선 / 루프 드릴다운 네비게이션 / 루프 노드 물결 헤일로 비주얼 / Input Slots 원칙)을 "확정" 표에 추가.
- Loop Anchor / Loop Lens 관련 기존 확정 항목은 삭제하지 않고 "`loop.guard` 1급 노드 설계(2026-08-07)로 이미 코드가 제거됨, 이번 드릴다운 설계는 그 위에 신규로 얹는 것"이라고 표기해 이력으로 남긴다.
- 나머지 미해결 항목(중심 노드 자동 선정, classic renderer 병행 기간, 노드 지름, Coordinator/Tool/Memory 노출, `LoopPolicy` 직렬화 — 이미 `loop.guard` 노드 설계로 대체되어 사실상 해소됨 여부 확인 필요)은 이번 범위 밖으로 그대로 열어둔다.

## 영향받는 코드 (구현 단계 참고용, 상세 설계는 후속)

| 영역 | 파일 | 변경 방향 |
| --- | --- | --- |
| 엣지 라우팅 | `ui/src/canvas/edges/AgentEdge.tsx`, `ui/src/canvas/nodes/radialPortGeometry.ts` | 정방향은 직선 경로로 전환(quantized Position 접선 계산 불필요), loop-back 판별 후 곡선+점선+loop-purple 분기 |
| 루프 접힘 노드 | `ui/src/canvas/nodes/` 신규 컴포넌트, `AgentNode.tsx` | 물결 헤일로 스타일(기존 running glow 재사용) + 코너 배지 |
| 드릴다운 네비게이션 (신규) | `ui/src/canvas/Canvas.tsx`, `ui/src/app/Toolbar.tsx`, 신규 뷰 상태(스토어 또는 로컬 state) | 현재 뷰 레벨(메인/특정 루프 내부) 상태 추가, breadcrumb 렌더. 참고할 기존 패턴 없음(순수 신규) |
| Input Slots | `ui/src/panels/Inspector.tsx` | `ModelSlotsEditor`와 동일 패턴의 신규 `InputSlotsEditor` (백엔드 계약은 후속 설계) |

## 테스트 관점 (구현 단계에서 구체화)

- 엣지: 대각선 방향 연결에서 직선 경로가 정확히 경계-경계로 그려지는지, loop-back 판별 로직이 오탐 없이 곡선 스타일을 적용하는지.
- 루프 접힘 노드: 멤버 수 배지, 접힌 상태에서도 실제 manifest 출력 포트(분기 포함)가 노출되는지.
- 드릴다운: 진입/복귀 시 Inspector 선택 상태·LogPanel 이벤트가 유지되는지(뷰 레벨 전환이 실행 상태에 영향을 주지 않는다는 원칙의 회귀 테스트), breadcrumb 네비게이션.

## 후속 작업 (이번 설계 범위 밖)

- Input Slots의 백엔드 계약(manifest 스키마, `compile.py` 배선, prompt 조립) 설계.
- `DECISIONS.md` 나머지 결정 대기 항목(중심 노드 선정, 노드 지름 등) 별도 세션에서 처리.
- 드릴다운이 여러 단계로 중첩되는 경우(루프 안에 루프)의 breadcrumb 처리 — 현재 스타터 그래프에는 중첩 루프 사례가 없어 이번 설계에서 다루지 않았다.
