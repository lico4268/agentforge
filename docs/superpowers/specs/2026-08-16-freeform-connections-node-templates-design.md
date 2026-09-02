> 🔁 **2026-09-02 텍스트 우선 전환으로 대체됨** — 이 문서가 다루는 노드 캔버스(React
> Flow)·Inspector·노드 팔레트·`custom.node`의 캔버스 인스턴스 편집 UX는 모두
> 삭제됐다. 저작은 이제 `server/arch/*.yaml` 텍스트이고, 노드 역할을 사용자가
> 정한다는 원칙(§2~4, [DIRECTION.md](../../../DIRECTION.md) §2~3)만 계승된다 —
> 계승한 형태는 `custom.node`가 파서가 만드는 유일한 사용자 노드 타입이라는 점.
> 현재 설계는 `2026-09-02-text-first-architecture-design.md`, 삭제 작업 기록은
> `.superpowers/sdd/2026-09-02-text-first-architecture/task-7-report.md` 참고.

# 프리폼 연결 + 노드 타입 템플릿 — 설계

- **작성일**: 2026-08-16
- **상태**: Phase A1 구현·머지 완료(`worktree-freeform-connections-phase-a1`). Phase A2(디스패치 정규화 — `compile.py`의 `review.intent`/`human.checkpoint`/`loop.guard` 노드 생성·엣지 배선 분기를 `manifest["runtime"]` 기준으로 전환) 구현 완료(2026-08-22, 커밋 예정) — `_CONDITIONAL_ROUTING_TYPES`/`loop_node_ids` 등 타입 문자열 기반 나머지 지점은 이번 범위 밖으로 남겨둠(YAGNI, 필요해지면 확장). Phase B ①(출력 스키마 동적화) 구현 완료(2026-08-22) — `LLM_STEP_TABLE` 삭제, `_build_output_model`/`_llm_step_spec`/`_output_write_keys`가 매니페스트 `defaults.outputSchema`(+ 신규 필드 `outputKeyMap`/`extraInputs`)에서 즉석 Pydantic 모델·state 키 매핑·`writes`를 전부 유도. 알려진 트레이드오프: `ReasonOut.confidence`의 `ge=0/le=1` 제약이 태그 기반 동적 모델에는 표현 불가해 사라짐(하드 라우팅에 안 쓰이는 참고 지표라 영향 낮음). Phase B ②(`AgentState.vars`) 구현 완료(2026-08-22) — `state.py`에 `vars: Annotated[dict[str, Any], merge_vars]` 필드 + `KNOWN_STATE_KEYS`(`AgentState.__annotations__` 기반 자동 유도) + `read_state_value`/`write_state_value` 추가. `nodes/llm_step.py`의 입력 읽기, `compile.py`의 `_make_llm_step_node` 출력 쓰기 둘 다 이 두 함수를 거치도록 전환 — 기존 필드(task/plan/answer/...)는 전부 `KNOWN_STATE_KEYS`에 있어 동작 변화 없음, `AgentState`에 없는 새 role만 `vars`에 담긴다. Phase B ③(매니페스트 저장소 CRUD) 구현 완료(2026-08-22) — 스펙 원안보다 범위가 좁아짐: Phase A2+B①/②로 7개 런타임 전부 이미 매니페스트만으로 새 타입을 만들 수 있는 상태라(`BUILTIN_MANIFESTS`에 하드코딩된 런타임별 실행 로직 자체는 무변경), 남은 건 저장·조회·삭제뿐이었다. `server/node_types.py` 신설(`/api/architectures`와 동일한 파일 기반 패턴, `server/node_types/<type>.json`) — `GET/POST /api/node-types`, `DELETE /api/node-types/{type}`, `GET /api/nodes`는 `BUILTIN_MANIFESTS + 커스텀 매니페스트`를 합쳐 반환. `NodeTypeManifest`(Pydantic)로 POST 요청 검증(runtime/category 화이트리스트, BUILTIN 타입 이름 덮어쓰기 금지) — 사용자 입력 경계라 `BUILTIN_MANIFESTS`(신뢰된 코드)와 달리 검증을 강제한다. PUT은 만들지 않음(POST가 upsert, architectures와 동일 관례). Phase B ④는 원안(재사용 가능한 "타입"을 등록하는 Node Type Builder 폼 + `/api/node-types` CRUD 연동)이 사용자 재확인 후 **더 단순한 설계로 대체돼 구현 완료**(2026-08-22): 새 타입을 등록하는 별도 폼이 아니라, 매니페스트가 완전히 빈 노드 타입 `custom.node` 하나(runtime `llm_step`, `inputs`/`outputs`: `[]`)를 캔버스에 놓고 그 **인스턴스마다** Inspector에서 이름·입출력 포트(+/-, 전부 텍스트 타입, 타입 선택 UI 없음)·시스템 프롬프트를 직접 채우는 방식. `server/node_types.py`(B③)의 REST CRUD는 이 흐름에서 쓰이지 않는다 — 죽은 코드는 아니고(독립적으로 완결된, 향후 "재사용 가능한 타입 저장" 용도가 생기면 쓸 수 있는 기능이지만 미배선 상태), 이 화면과는 별개다.

구현: `server/graphs/compile.py`의 `_effective_output_schema(node, manifest)`가 매니페스트에 `outputSchema`가 없으면 이 노드 인스턴스의 `config.outputs` 포트에서 즉석 유도(전부 `"string"` 취급); `_llm_step_spec`/`_make_llm_step_node`가 `node`(인스턴스) 전체를 받도록 시그니처 확장돼 `config.inputs`/`config.outputs`를 매니페스트보다 우선 사용. 프론트: `GenericNode.tsx`/`AgentNode.tsx`가 `config.inputs`/`config.outputs`/`config.label`을 매니페스트보다 우선 사용(다른 타입은 이 config 키를 절대 안 채우므로 무변화); `Inspector.tsx`에 `PortListEditor`(기존 `ModelSlotsEditor`의 add/remove 패턴 재사용) + Name 필드 신설, `manifest.type === 'custom.node'`일 때만 노출. 포트 id는 라벨과 무관하게 생성 시점에 한 번 발급(`nextPortId`, 기존 `nextSlotId`와 동일 패턴) — 라벨을 나중에 바꿔도 이미 연결된 엣지가 안 깨진다.
- **계보**: `2026-08-15-freeform-port-connector-design.md`(캔버스 뷰 레이어만 재설계, `Architecture`/`compile_graph` 비목표로 명시)의 다음 단계. 또한 `2026-08-14-ui-canvas-design-philosophy-design.md` §5(In/Out 포트 설정 원칙)가 "Input Slots의 백엔드 계약... 후속 설계로 넘긴다"고 예고했던 바로 그 후속 설계 — 다만 도달한 메커니즘은 그 문서가 스케치했던 "`ModelSlotsEditor`처럼 Inspector에서 수동 추가/삭제"가 아니라 **"캔버스에서 그은 연결 자체가 슬롯"** 쪽으로 갈라졌다(§2 참고, 이유 명시).
- **범위**: 포트/연결 데이터 모델, 캔버스 연결 UX, Inspector 역할 배정 UX, 백엔드 컴파일러(`compile_graph`) 변경, 노드 타입 확장성(템플릿).

## 배경 / 문제

지금 노드 "타입"(`planning.decompose`, `reasoning.cot`, `review.intent` 등)은 백엔드 `BUILTIN_MANIFESTS`(`server/manifests.py`)에 고정된 `inputs`/`outputs` 포트 목록(`id`/`label`/`dataType`/`required`)을 하드코딩하고 있고, 같은 타입의 모든 노드 인스턴스가 그 포트 구성을 그대로 물려받는다. 사용자가 제기한 불만 3가지:

1. **인스턴스별 포트 편집 불가** — 같은 타입의 노드는 전부 똑같은 포트를 가짐.
2. **노드 타입 자체가 폐쇄적** — 새 타입을 추가하려면 Python 코드(`BUILTIN_MANIFESTS`)를 고쳐야 함, 캔버스에서 사용자가 할 수 있는 일이 아님.
3. **포트가 의미론에 너무 묶임** — `task`/`plan`/`answer`처럼 포트가 특정 역할·`dataType`에 고정되어 있어 자유로운 연결이 어렵고, 고정 위치 렌더링과 겹쳐 캔버스에서 선이 얽혀 보임.

`2026-08-15` 설계(직전 5개 커밋으로 이미 shipped)는 (3)의 **시각적** 증상만 풀었다 — 미연결 포트를 hover-reveal 라벨 목록으로 바꿔 항상 고정 위치를 차지하지 않게 했지만, 포트의 **의미**(캔버스 특정 지점에 정확히 드래그해야 하는 것)는 그대로 뒀고 `Architecture`/`compile_graph`는 의도적으로 건드리지 않았다.

### 백엔드 재조사로 확인한 핵심 사실

`llm_step` 계열 노드(Planning/Reasoning 등)는 입력을 엣지로 "배선"해서 받지 않는다 — `_make_llm_step_node`가 매니페스트의 `inputs` 목록을 그대로 `input_keys`로 쓰고, `run_llm_step`이 `state.get(state_key)`로 공유 `AgentState`에서 고정 키 이름을 직접 읽는다. 엣지는 사실상 LangGraph 실행 순서(토폴로지)만 결정한다(`_filter_control_edges`의 주석이 이를 명시). 반면 `review.intent`/`loop.guard`/`human.checkpoint`의 분기 출력(`accept`/`refine`/`clarify`, `loopBack`/`exit`, `approve`/`revise`/`reject`)은 `sourceHandle` 문자열이 실제로 `add_conditional_edges` 라우팅에 쓰인다. 즉 **일반 데이터 포트와 분기 포트는 이미 백엔드에서 다른 방식으로 동작**하고 있었다 — 이 설계는 그 비대칭을 그대로 인정하고 각각 다르게 취급한다.

## 목표

- 일반 데이터 포트는 완전 프리폼(위치·개수·라벨 무관)으로 연결 가능하게 한다.
- 분기 출력(`review`/`loop_guard`/`checkpoint` 런타임)은 여전히 정확한 역할 배정이 필요하지만, 그 배정을 캔버스가 아니라 Inspector에서 하게 한다.
- 새 노드 타입을 코드 변경 없이 사용자가 만들 수 있게 한다(단, 실행 로직 자체는 기존 7개 runtime으로 제한).
- 지금 존재하지 않는 검증(필수 입력 누락, 분기 미배정, 분기 중복 배정)을 새로 추가해, 프리폼화가 지금 캔버스가 암묵적으로 해주던 안전장치를 없애지 않게 한다.
- 캔버스 UI 철학(`2026-08-14` 문서 §1)을 그대로 따른다 — 캔버스는 흐름만 보여주고, 설정은 전부 Inspector로.

## 비목표

- 사용자가 완전히 새로운 실행 로직(커스텀 코드)을 정의하는 것 — 플러그인 시스템 규모, 별도 과제.
- 필수 입력의 완전한 must-reach 정적 분석(조건부 분기의 일부 경로에만 writer가 있는 경우) — §6에서 범위 제외 사유와 대안(매니페스트 컨벤션) 명시.
- 기존 `AgentEdge.tsx`의 엣지 경로(직선/곡선) 렌더링 방식 — `2026-08-14` 설계 그대로 유지.
- Loop Scope collapse/drilldown의 **로직 자체**(멤버 판정 알고리즘, drilldown 네비게이션) 재설계 — 그건 안 건드린다. 다만 그 로직이 `sourceHandle`을 직접 읽는 지점들은 이 설계가 `sourceHandle`을 불투명화하므로 명시적으로 함께 고쳐야 한다(§7, 자동으로 안 얹힘 — Opus 검증에서 확인된 사실로 최초 초안의 "자동으로 얹힌다" 주장을 정정).

## 아키텍처

### 0. 단계 구성

- **Phase A1 — 연결 모델**: 프리폼 포트 + 엣지 레벨 role + AND/OR join 선언 + 관련 컴파일러 검증. 역할 카탈로그(`task`/`plan`/`answer`, `accept`/`refine`/`clarify` 등)는 코드에 남김.
- **Phase A2 — 디스패치 정규화**: `compile.py`의 `elif node_type == "review.intent"` 식 타입별 분기를 `manifest["runtime"]` 기준으로 정규화. Phase B가 새 타입을 추가해도 디스패치 코드를 안 건드리게 하는 사전 작업.
- **Phase B — 노드 타입 템플릿**: `LLM_STEP_TABLE`의 `output_model`/state 매핑을 매니페스트 `defaults.outputSchema`에서 동적 생성 + `AgentState`에 범용 `vars: dict` 필드 추가 + `BUILTIN_MANIFESTS`를 CRUD 가능한 저장소로 이전 + Node Type Builder UI.

A가 B보다 먼저인 이유: B의 "역할 카탈로그를 사용자가 정의"는 A가 만드는 "역할은 캔버스 위치가 아니라 엣지에 붙는 데이터"라는 기반 위에서만 재작업 없이 성립한다.

### 1. 데이터 모델 (Phase A1)

`GraphEdgeSchema`에 필드 추가 (`GraphNode`는 역할 관련해서 변경 없음 — role은 엣지 소유):

```ts
export const GraphEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  sourceHandle: z.string(),   // 불투명 슬롯 id — 캔버스가 연결 시 내부 생성, 사용자는 안 봄
  target: z.string(),
  targetHandle: z.string(),   // 동일
  sourceRole: z.string().optional(),  // review/loop_guard/checkpoint 출력에서만 의미 있음
})
```

`targetRole`은 추가하지 않는다 — 데이터 입력 포트는 역할 개념 자체가 필요 없다(검증기가 엣지 role이 아니라 그래프 도달 가능성으로 판단, §5). 쓰이지 않는 필드를 미리 넣지 않는다.

`GraphNodeSchema`에 필드 추가 (AND/OR join, §4):

```ts
joinMode: z.enum(['and', 'or']).optional()  // §4의 조건을 만족할 때만 의미 있음, 그 경우 필수
```

**마이그레이션이 공짜인 이유**: 지금 저장된 모든 Architecture의 `sourceHandle`이 이미 역할 이름 그 자체다(`"accept"`, `"refine"` 등). 백엔드가 `edge.get("sourceRole") or edge["sourceHandle"]`로 읽으면, 기존 저장 파일·`starterArchitecture.ts`·고정 `gsm8k-treatment` 그래프가 전부 코드 변경 없이 계속 동작한다.

`NodeManifest`의 `inputs`/`outputs`(`Port[]`) 스키마는 **그대로 유지**하되 의미가 바뀐다 — 캔버스 렌더 타겟이 아니라 Inspector 드롭다운의 역할 카탈로그(메뉴) 소스가 된다.

### 2. 캔버스 연결 UX

**일반 데이터 포트** (모든 노드의 비-분기 입출력): 완전 프리폼. 노드 경계 아무 데서나 드래그 시작/종료. 라벨도 번호도 없음 — 사용자가 신경 쓸 게 없다. `sourceHandle`/`targetHandle`은 캔버스가 내부적으로 생성하는 불투명 id일 뿐.

**분기 출력** (`manifest.runtime ∈ {review, loop_guard, checkpoint}`): 드롭하는 순간 뜨는 팝업 메뉴는 **채택하지 않는다** — 캔버스에 인터랙티브 요소를 추가하는 것이라 원칙(캔버스=흐름, 설정=Inspector)에 어긋난다. 대신:

- 새로 그은 분기 엣지는 **"미배정" 시각 상태**(중립 회색 점선)로 그려진다. 기존 accept=초록/clarify=주황/reject=빨강 색상 코딩과 확실히 구분되는 스타일이어야 한다 — 지금 `edgePresentation.ts`가 `refine`을 별도 색 없이 기본값(`#6f8175`, 회색빛)으로 떨어뜨리고 있어서 그대로 "미배정" 색으로 쓰면 "배정된 refine"과 구분이 안 된다. `refine`에 고유 색을 새로 주고, "미배정"은 그 어떤 배정 색과도 겹치지 않는 스타일로 간다.
- **미배정 엣지를 클릭하면 소스 노드가 선택되고 Inspector가 그 노드의 "나가는 분기" 섹션으로 자동 스크롤**된다. 이 연결이 없으면 회색 선을 보고도 사용자가 뭘 해야 할지 모른다 — "캔버스가 Inspector로 명확히 안내해야 한다"는 원칙을 이 클릭 동작이 실제로 구현한다.
- 역할이 배정되면 엣지가 기존 색상 코딩으로 즉시 전환된다 — 배정 후에는 캔버스만 보고도 의미를 알 수 있다(Inspector를 다시 열 필요 없음). "미배정 → Inspector 유도" 신호는 미배정일 때만 필요하다.

새로 생기는 캔버스 쪽 인터랙티브 요소는 딱 하나 — "미배정 엣지 스타일 + 클릭 시 Inspector 이동"이다. 나머지는 전부 Inspector.

### 3. Inspector UX

**나가는 분기 목록** (분기 런타임 노드에만 표시): 각 행은 **타겟 노드의 라벨**로 표시된다("→ Output", "→ Reasoning") — 엣지 id나 슬롯 번호가 아니라, 실제로 어디로 가는지가 바로 보여야 사용자가 직관적으로 역할을 고를 수 있다. 행마다 역할 드롭다운(그 노드 타입의 역할 카탈로그에서). 같은 소스 노드의 다른 엣지에 이미 배정된 역할은 드롭다운에서 비활성화(§5의 중복 배정 방지). 행에 마우스를 올리면 캔버스에서 해당 엣지가 하이라이트(읽기 전용 피드백 — 새 캔버스 조작 UI가 아니므로 원칙에 안 어긋남). 이건 두 분기가 같은 타겟으로 가는 드문 경우("→ Output"이 두 줄)에 어느 게 어느 건지 구분하기 위함이다.

**join mode 선택** (§4의 조건을 만족하는 노드에만 표시): "이 노드는 들어오는 연결을 전부 기다려야 하나(AND) / 아무거나 하나만 오면 실행되나(OR)"를 묻는 필수 선택지. 기본값 없음 — 애매하면 반드시 사용자가 정하게 강제한다.

### 4. AND/OR join — 실제 동기화까지 구현

**Opus 코드 검증에서 드러난 사실**: `review.intent`(`add_conditional_edges`), `human.checkpoint`/`loop.guard`(`Command(goto=...)`)는 애초에 일반 `add_edge`를 호출하지 않는다 — LangGraph의 join-edge(`add_edge([...], target)`)는 `add_edge`로 등록된 소스만 묶을 수 있으므로, **이 세 런타임이 소스인 엣지는 구조적으로 AND에 참여할 수 없다.** `starterArchitecture.ts`의 `output`(들어오는 엣지 3개, 전부 review/checkpoint/loop_guard발)·`reasoning`(3개)이 실제 사례 — 전부 이 부류라 애초에 AND를 고를 수 있는 상황이 아니다. 이걸 빼고 "필수 선택"을 적용하면 스타터 그래프가 로드 시점에 무효가 되어 §1 "마이그레이션 공짜" 주장이 깨진다.

**수정된 규칙**: 노드로 들어오는 엣지들을, `_filter_control_edges` 적용 **후**의 그래프 기준으로(실제 LangGraph가 보는 그래프와 일치시키기 위해) 소스의 런타임별로 나눈다.

- 들어오는 엣지가 전부 plain-edge 런타임(`llm_step`/`io`/`model`)에서 온 것이고 개수가 2개 이상이면 → `joinMode` **필수 선택**(AND/OR), 위 두 방식대로 컴파일.
- 들어오는 엣지 중 하나라도 conditional-routing 런타임(`review`/`loop_guard`/`checkpoint`)에서 온 것이면 → `joinMode`는 **표시하지 않고 항상 OR**(선택 불가, AND가 애초에 불가능하므로). 개별 `add_edge`/기존 conditional 라우팅 그대로.

이 조건에서 OR: 개별 `add_edge`. 두 경로가 다른 수퍼스텝에 끝나면 노드가 두 번 트리거될 수 있다는 LangGraph의 기존 한계는 그대로 남는다(OR 선언이 이 문제를 풀어주지 않는다, 있는 그대로의 동작을 명시적으로 인정하는 것). AND(plain-edge 소스만 있을 때만 선택 가능): `compile_graph`가 그 노드로 들어오는 AND 선언된 소스를 전부 모아서, 개별 `add_edge` 대신 **`add_edge([source1, source2, ...], target)`** 한 번으로 등록한다.

**검증 완료** (Opus가 실제 설치 패키지 소스로 확인, 추측 아님): 프로젝트에 실제 설치된 langgraph는 **1.2.10**(`pyproject.toml`의 `>=0.2.0`은 하한선일 뿐 실행 버전이 아님). `graph/state.py:915`, `def add_edge(self, start_key: str | list[str], end_key: str)` — 리스트를 넘기면 "모든 시작 노드가 끝날 때까지 기다린다"는 docstring과 함께 `self.waiting_edges.add((tuple(start_key), end_key))`로 저장됨. 리스트의 모든 소스가 이미 `self.nodes`에 등록돼 있어야 하는데, `compile_graph`는 엣지 루프 전에 모든 노드를 먼저 추가하므로 순서 문제 없음.
  - 출처: [LangGraph's Execution Model is Trickier Than You Might Think](https://spin.atomicobject.com/langgraphs-execution-model-tricky/), [StateGraph Reference](https://reference.langchain.com/python/langgraph/graph/state/StateGraph), [Branching - LangGraph](https://www.baihezi.com/mirrors/langgraph/how-tos/branching/index.html), 설치된 패키지의 `graph/state.py:915` 직접 확인

**`_filter_control_edges`와의 관계**: 이 함수가 땜빵했던 원래 버그(`io.input`이 즉시 완료돼 `input→reasoning` 직결과 `input→planning→reasoning` 간접이 다른 수퍼스텝에 끝나면서 reasoning이 두 번 트리거)는 `io.input`(runtime `io`)과 `planning`(runtime `llm_step`) 둘 다 plain-edge 소스라 위 규칙의 "필수 선택" 버킷에 해당한다 — 이 두 엣지만 있는 상황이라면 AND로 선언 시 join-edge 메커니즘이 자연히 해결한다. 다만 실제 `starterArchitecture.ts`의 `reasoning`은 들어오는 엣지가 3개(`e2`/`e3`/`e9`)이고 `_filter_control_edges` 적용 후 2개로 줄어드는데, 그 2개가 전부 plain-edge 소스인지(AND 선택 가능) 아니면 conditional-routing 소스가 섞여 있는지(자동 OR)는 Opus 검증에서 확인되지 않았다 — 구현 착수 시 실제 `starterArchitecture.ts`를 읽어 확정한다. Phase A2에서 `_filter_control_edges` 자체를 좁히거나 제거할 수 있는지도 실제 구현 시 검증한다(현재는 "검증 필요" 항목으로만 기록 — 이 함수의 다른 호출 경로까지 전부 감사하지 않은 상태에서 제거를 단정하지 않는다).

### 5. 백엔드 (`compile.py`) 변경

- `edgePresentation()`, `isLoopBackEdge()` — `sourceHandle` 대신 `sourceRole or sourceHandle`(둘 중 있는 쪽)을 읽도록 이전.
- `_handle_targets()`, `_validate_loop_guard_ports()`, `make_route_review()`의 `wired` 집합 — 전부 resolved role 기준으로 변경.
- **신규: 미배정 분기 하드 에러** — 분기 런타임 노드의 나가는 엣지 중 `sourceRole`이 없는 게 있으면 컴파일 타임에 에러. 지금까지의 폴백 체인(`clarify > refine > accept`)은 "일부만 배정된" 상황을 구제해주지 않는다 — 배정 자체가 없는 핸들은 매칭될 수 없어 런타임에 `ValueError`로 죽거나(`review`), `human.checkpoint`처럼 조용히 전부 `END`로 빠진다. 실행 전에 막는다.
- **신규: 분기 중복 배정 하드 에러** — 같은 소스 노드의 두 엣지에 같은 role이 배정되면(`_handle_targets`가 dict라 나중 게 조용히 덮어씀) 컴파일 에러. `loop.guard`용으로 이미 있는 `_validate_loop_guard_ports`와 같은 부류를 `review`/`checkpoint`에도 일반화.
- **신규: 필수 입력 검증기** (§6).
- **신규: AND join 컴파일** (§4).

### 6. 필수 입력 검증기 — 2단계로 축소

지금은 `required: true`가 매니페스트에만 존재하고 어디서도 읽히지 않는다(`run_llm_step`은 값이 없으면 그냥 건너뜀) — 즉 **지금은 캔버스가 유일한 검증 수단**이고, 프리폼화는 이 암묵적 검증마저 없앤다.

**Tier 1 (구현함, 하드 에러)**: "이 필수 역할을 쓰는 노드가 그래프 전체에 단 하나도 없다." 사이클 포함 전체 그래프에서 도달 가능성만 보는 단순 존재 체크(may-분석) — AND/OR 구분도, 백엣지 제외도 필요 없다. `task`/`task_tags`/`intent`/`criteria`/`batch_mode` 등 `initial_state()`(WS run 메시지)에서 오는 필드는 애초에 "항상 충족됨"으로 미리 시드해둔다 — `io.input` 노드가 캔버스에 없어도 정상인 그래프를 오탐으로 막지 않기 위해서다. `human.checkpoint`의 `edits`(임의 키 추가)는 분석 불가능하지만 순수 추가적이므로 무시한다. 존재 자체가 없으면 100% 확실한 실수(오탐 없음) — "필수 입력을 아예 안 배선했다"는 가장 흔한 실수를 잡는다.

**Tier 2 (구현 안 함, 범위 명시적 제외)**: "일부 경로에만 writer가 있다"(예: `review.intent`의 refine 분기에서만 쓰는 `feedback`을 `Reasoning`이 필수로 요구) — 정확히 판별하려면 조인 지점마다 AND(합집합)/OR(교집합)를 구분하는 진짜 정적 데이터플로우 분석(컴파일러의 definite-assignment 분석과 동급)이 필요하고, 백엣지도 분석에서 제외해야 한다(루프 안에서만 채워지는 값은 1회차엔 없음). 구현 비용이 이 프로젝트 전체 범위보다 커질 수 있어 이번엔 만들지 않는다.

**대안**: 특정 분기에서만 채워지는 값은 매니페스트에서 애초에 `required: false`로 선언하는 컨벤션을 따른다. `required: true`는 "모든 실행 경로에서 항상 채워짐"이 참인 값에만 쓴다(예: `io.input`이 항상 주는 `task`). 이 컨벤션이 지켜지면 Tier 1만으로 오탐 없이 충분하다.

### 7. Loop Scope 프론트 — `sourceHandle` 불투명화의 실제 영향 (Opus 코드 검증에서 발견)

`sourceHandle`이 의미 있는 문자열이라는 전제로 짜인 프론트 코드가 최소 3곳 있다. §비목표에서 "자동으로 얹힌다"고 썼던 최초 주장은 틀렸다 — 이 설계의 명시적 작업 범위에 포함한다:

- `ui/src/canvas/loop/deriveLoopMembers.ts:20` — `e.sourceHandle === 'loopBack'`으로 매칭. `sourceRole === 'loopBack'` 기준으로 변경(§1의 `sourceRole or sourceHandle` 해석 규칙과 동일 패턴).
- `ui/src/canvas/loop/loopProjection.ts:34` — `edge.sourceHandle ?? edge.id`를 **사용자에게 보이는 라벨**로 그대로 사용. 불투명 id가 되면 의미 없는 문자열이 노출된다 — `sourceRole`이 있으면 그걸, 없으면(일반 데이터 엣지) 라벨 자체를 안 보이거나 다른 방식(예: 타겟 노드 이름)으로 대체해야 한다. 90/101행의 `sourceHandle` 재작성 로직도 함께 점검.
- `ui/src/canvas/nodes/hubRimAngles.ts:67` — `sourceHandle === port.id`로 매칭. 불투명 id 도입 후에도 성립하는지 별도 확인 필요(포트 개념 자체가 프리폼으로 바뀌므로 이 매칭 로직 전제가 더 근본적으로 바뀔 수 있음).

## Phase A2 — 디스패치 정규화

`compile.py`의 노드 생성 분기가 `elif node_type == "review.intent"` 식으로 타입 문자열에 직접 걸려 있다(`llm_step`류만 예외적으로 `manifest["runtime"]` 기반). 이걸 전부 `runtime` 기준으로 통일 — Phase B가 새 타입(다른 `type` 문자열, 같은 `runtime`)을 추가해도 디스패치 코드를 안 건드리게 만드는 사전 정지 작업.

## Phase B — 노드 타입 템플릿 (범위 재확정)

Phase B는 "매니페스트를 하드코딩 리스트에서 DB로 옮기기"보다 크다. 실제로 필요한 것:

1. **출력 스키마 데이터화**: `compile.py`의 `LLM_STEP_TABLE`이 타입별로 `output_model`(Pydantic 클래스)과 state 매핑을 하드코딩하고 있다. 사용자가 만든 `llm_step` 타입은 이게 없어 컴파일 불가능 — 매니페스트의 `defaults.outputSchema`(이미 존재하는 필드, 지금은 프론트 힌트 용도)에서 동적으로 생성하도록 바꿔야 한다.
2. **`AgentState.vars` 범용 필드**: `AgentState`는 고정 `TypedDict`라 사용자 정의 역할 키가 저장될 자리가 없다. `vars: dict[str, Any]` 같은 범용 버킷을 추가하고, 사용자 정의 role은 여기 읽고 쓰게 한다.
3. **저장소 이전**: `BUILTIN_MANIFESTS`를 파일/DB 기반으로 옮기고 REST CRUD(`GET/POST/PUT/DELETE /api/node-types`) 추가.
4. **Node Type Builder UI**: 런타임 7종(`llm_step`/`review`/`checkpoint`/`policy`/`model`/`io`/`loop_guard` — 닫힌 채로 유지, 실제 Python 실행 로직이므로) 중 하나를 고르고, 자기만의 역할 카탈로그·config 스키마·프롬프트·기본값을 조합하는 폼. 1~3이 끝나야 실제로 컴파일 가능한 타입을 만들 수 있으므로 그 다음 순서.

## 영향받는 파일 (참고용)

| 영역 | 파일 |
| --- | --- |
| 데이터 모델 | `ui/src/types/graph.ts`, `server/`의 대응 Pydantic(있다면) |
| 캔버스 연결 | `ui/src/canvas/nodes/RadialNodePorts.tsx`, `radialPortGeometry.ts`, `ui/src/canvas/edges/edgePresentation.ts`, `AgentEdge.tsx` |
| Inspector | `ui/src/panels/Inspector.tsx` (분기 목록 + join mode 섹션 신규) |
| Loop Scope (§7, 신규 발견) | `ui/src/canvas/loop/deriveLoopMembers.ts`, `ui/src/canvas/loop/loopProjection.ts`, `ui/src/canvas/nodes/hubRimAngles.ts` |
| 컴파일러 | `server/graphs/compile.py`(`_handle_targets`, `_validate_loop_guard_ports`, `_filter_control_edges` 재검토, 신규 검증기·AND join). `_make_llm_step_node`는 Phase A1에서 **변경 없음** — `input_keys`는 Phase B(출력 스키마 데이터화)까지 매니페스트 기반 그대로 유지 |
| 라우팅 | `server/nodes/policy.py`(`make_route_review`) |
| Phase B | `server/manifests.py` → 저장소 이전, `server/state.py`(`AgentState.vars`), 신규 REST 라우트, 신규 Node Type Builder 패널 |

## 테스트 전략

- `server/tests/test_compile.py`는 이미 존재한다(812줄, 20개 이상 테스트 — `CLAUDE.local.md`의 "밀려있던 작업"이라는 메모는 낡은 정보였다, Opus 코드 검증으로 확인). 이번 작업은 **신설이 아니라 확장**이다. 다만 공유 테스트 헬퍼 `_edge()`(`source_handle="out"` 기본값)에 `source_role` 파라미터를 추가해야 하는데, 이건 **기존 테스트 전부에 영향**을 준다 — 이 마이그레이션 자체를 별도 작업 항목으로 잡는다. 추가로: role 해석, 미배정/중복 배정 에러, Tier 1 필수 입력 검증기(사전 시드 키 포함), AND join의 `add_edge` 호출 형태(§4의 plain-edge/conditional-routing 소스 분기 포함).
- 프론트: `radialPortGeometry.ts`/`edgePresentation.ts` 신규 로직 단위 테스트, Inspector 분기 목록·join mode 섹션 RTL 테스트, §7의 세 파일에 대한 회귀 테스트(불투명 id 도입 후에도 loop 멤버 판정·라벨·hubRim 매칭이 깨지지 않는지).
- 마이그레이션 회귀: 기존 저장된 Architecture(특히 `starterArchitecture.ts`, 고정 `gsm8k-treatment`)가 `sourceRole` 없이도 그대로 컴파일되는지 — `output`/`reasoning`처럼 conditional-routing 소스가 섞인 다중 in-degree 노드가 §4 수정 규칙대로 `joinMode` 없이도 유효한지 반드시 포함.
- 실제 드래그-드롭 연결 생성은 이 샌드박스에 헤드리스 브라우저가 없어 자동 검증 불가 — 사용자가 `npm run dev`로 직접 확인.

## 미해결 세부사항 (구현 계획 단계에서 확정)

- "미배정" 엣지 스타일의 정확한 색/두께 값.
- Inspector 분기 목록·join mode 섹션의 정확한 레이아웃(기존 `ModelSlotsEditor`/Connections 섹션 스타일 재사용 정도).
- `_filter_control_edges`를 AND join 도입 후 좁힐지 완전히 제거할지 — 다른 호출 경로 감사 필요.
- Node Type Builder UI의 정확한 폼 구성(Phase B 착수 시).
- `starterArchitecture.ts`의 `reasoning`(필터 후 in-degree 2)이 §4의 plain-edge 버킷(AND 선택 가능)인지 conditional-routing 버킷(자동 OR)인지 — 구현 착수 시 확정.
