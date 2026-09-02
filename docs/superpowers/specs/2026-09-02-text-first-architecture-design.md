# 텍스트 우선 아키텍처 저작 — 설계

- 날짜: 2026-09-02
- 상태: 승인됨 (브레인스토밍 완료, 구현 계획 대기)
- 대체: 노드 캔버스(React Flow)를 아키텍처 **저작** 수단으로 쓰던 방식

## 1. 문제

캔버스가 시스템 개발의 병목이다. 에이전트 그래프를 만들려면 노드를 배치하고,
포트를 잇고, Inspector 폼을 채워야 한다. 정작 설계에 해당하는 정보는 얼마 안 되는데
캔버스가 자기 그림을 그리려고 요구하는 부기(bookkeeping)가 그 위를 덮는다.

스타터 그래프 45줄(`ui/src/app/starterArchitecture.ts`) 중:

- `position` 8개 — 배치는 정보가 아니다
- 엣지 id `e1`~`e11` — 사람이 붙일 이유가 없다
- `sourceHandle`/`targetHandle` 22개 — 포트 이름 수동 매칭
- `loop_reentry` 노드 — `PASSTHROUGH_TYPES`(`compile.py:94`), 즉 루프 재진입을
  *그리기* 위해서만 존재하는 노드

ComfyUI를 참조하면서 "노드를 배치한다"까지 따라왔지만, ComfyUI는 이미지
파이프라인이라 공간 배치가 실제 정보를 담는다. 에이전트 그래프는 아니다.

두 번째 문제: 노드가 고정 카탈로그(`planning.decompose`, `reasoning.cot`,
`review.intent`…)에서 골라 쓰는 것이라, 사용자가 머릿속 구조를 표현하려면 매번
기존 노드 역할에 자기 의도를 번역해 끼워 맞춰야 한다. 이는 `DIRECTION.md`가
무효화한 방향이며, `custom.node`(Phase B④)에서 이미 인스턴스별 자유 정의로
방향이 잡혔지만 캔버스에서는 여전히 예외적 타입 하나에 머물러 있다.

## 2. 방향

**아키텍처는 텍스트로 짓고, 그림은 그 텍스트에서 자동 생성되는 읽기 전용 산출물로
만든다.** 사람은 좌표를 정하지 않는다.

**노드는 사용자가 그때그때 정의한다.** 사전 정의 노드는 사용자가 프롬프트로 만들 수
없는 것 — 경계(`input`/`output`)와 런타임 장치(`human.checkpoint`/`loop.guard`) —
넷뿐이다.

실행 계층(`server/graphs/`, `server/nodes/`, `events.py`, `workspace.py`, WS
프로토콜)은 건드리지 않는다. 이번 전환은 표현 계층 교체이며, 분기 일반화(§5)만
런타임에 손을 댄다.

## 3. `arch.yaml` 포맷

`flow:`는 **mermaid flowchart 문법 그대로**다. 자체 문법을 만들지 않는다.

```yaml
name: GSM8K Treatment
model: google/gemini-3.1-flash-lite      # 기본 모델. 노드가 덮어쓸 수 있음

flow: |
  input --> planning --> reasoning --> review
  review -->|ok|    output
  review -->|retry| reasoning

nodes:
  planning:
    in:  [task]
    out: [plan]
    prompt: |
      문제를 풀 단계로 쪼개라. 각 단계 한 줄씩.

  reasoning:
    in:  [task, plan]
    out: [answer]
    prompt: |
      계획을 따라 풀어라.

  review:
    in:  [task, answer]
    out: [verdict]
    model: opus-5                        # 이 노드만 다른 모델
    prompt: |
      답이 맞는지 봐라.
```

### 3.1 규칙

배울 문법은 `-->`와 `|라벨|` 둘뿐이다.

1. **화살표는 순서, 노드 정의는 데이터.** `a --> b`는 실행 순서만 정한다. 어떤 값이
   오가는지는 각 노드의 `in:`/`out:` 이름이 결정한다. 따라서 엣지에
   `sourceHandle`/`targetHandle`이 없다.
2. **노드 = 이름 + 프롬프트 + `in`/`out`.** 타입을 고르지 않는다. 이름은 자유이며
   한글도 된다. `out:`은 개수 제한이 없다.
3. **라벨은 어휘가 아니라 문자열이다.** 파서는 `ok`/`retry`가 뭔지 모른다. 아무
   문자열이나 쓸 수 있고 분기 개수 제한도 없다.
4. **사전 정의 노드는 `run:`으로만 쓴다.** `{ run: human.checkpoint }`,
   `{ run: loop.guard, max: 3 }`.
5. **`in:`의 이름 뒤 `?`는 선택 입력이다.** 아직 아무 노드도 만들지 않은 값을
   받겠다는 선언. 런타임 변경은 없다 — `llm_step.py:71`이 이미 `None` 값을 프롬프트
   블록에서 건너뛴다. `?`는 "이 이름을 만드는 선행 노드가 없다"는 파서 검증을
   면제하는 표시일 뿐이다. 루프 회차 간 피드백 전달에 쓴다(§5.1).

`in:`의 값들은 `## <이름>` 블록으로 프롬프트에 붙는다 — 템플릿 문법(`{{...}}`)은
없다.

### 3.3 이름이 곧 정체성

노드 타입이 없으므로 **이름이 노드를 구분하는 유일한 수단**이다. 같은 일을 하는
노드가 둘 있으면 하는 일로 이름을 나눠 짓는다 — 예전처럼 `reasoning` /
`reasoning_2`로 같은 타입의 인스턴스를 구별할 필요가 없다.

```yaml
flow: |
  input --> 초안 --> 검토 --> 재작성 --> output

nodes:
  초안:   { in: [task],                  out: [draft],    prompt: ... }
  검토:   { in: [task, draft],           out: [critique], prompt: ... }
  재작성: { in: [task, draft, critique], out: [answer],   prompt: ... }
```

주의 지점은 이름이 아니라 `out:`이다. 두 노드가 같은 출력 이름을 쓰면 `merge_vars`
규칙상 뒤 노드가 앞 노드 값을 덮어쓴다. **파서는 이때 경고를 낸다** — 덮어쓰기가
의도면 그대로 두고, 아니면 이름을 나누라는 뜻이다. 루프 안에서 같은 노드가 반복
방문하며 자기 출력을 덮어쓰는 것은 정상이므로 경고 대상이 아니다.

### 3.2 mermaid를 쓰는 이유

- 파서가 정규식 하나로 끝난다 (`(\w+)\s*-->(?:\|(.*?)\|)?\s*(\w+)` + 체인 분해)
- 그림 렌더링에 변환 코드가 0줄이다 — `flow:` 문자열을 mermaid에 그대로 넘긴다
- GitHub·Obsidian·노션·Claude 대화창에 붙여넣으면 그대로 그려진다

## 4. 삭제 / 유지

### 삭제 (~3,300줄)

- `ui/src/canvas/` 전부 (~1,100줄) — React Flow, 방사형 포트 지오메트리, 루프 투영
- `ui/src/panels/Inspector.tsx` (1,138줄)
- `ui/src/registry/builtinManifests.ts` (319줄), `panels/NodeLibrary.tsx` (119줄)
- `ui/src/stores/useGraphStore.ts`, `useUiStore.ts` (198줄)
- `ui/src/app/starterArchitecture.ts`, `OpenRouterFavoritesModal.tsx`
- `reactflow` 의존성
- 백엔드 노드 타입: `planning.decompose`, `reasoning.cot`, `review.intent`,
  `model.binding`, `loop.reentry`

`custom.node`는 **삭제하지 않는다.** "매니페스트가 빈 llm_step 노드"가 정확히 이
설계가 필요로 하는 것이라, 파서가 사용자 정의 노드를 이 타입으로 뱉으면
`compile_graph`가 지금 코드 그대로 컴파일한다. 사용자는 이 이름을 타이핑하지 않는다
(파서 내부 표현일 뿐이다).

`work/radial-agent-canvas/`의 Loop Scope 작업(Slice 6.5~10)은 이 삭제에 포함된다.
캔버스 view-layer 전용 투영이었으므로 실행 계층에는 영향이 없다.

### 유지

- 백엔드 실행 계층 전부 — `graphs/compile.py`, `nodes/`, `events.py`,
  `workspace.py`, `harness.py`
- **고정 그래프 `treatment.py`/`baseline.py`는 그대로 둔다.** 매니페스트 없이 직접
  `StateGraph`를 짓는 별도 경로라 노드 타입 삭제와 무관하며, GSM8K 벤치마크
  기준선이 보존된다.
- 프론트 재사용 (~900줄): `transport/`, `execution/`, `panels/LogPanel.tsx`,
  `panels/Markdown.tsx`, `types/events.ts`, `canvas/nodes/CheckpointActions.tsx`

### 신규 (~400줄)

- `server/archfile.py` (~120줄) — YAML → `Architecture` dict 파싱 + 검증
- `GET/POST /api/arch` — 파일 목록/내용 조회, 실행 요청
- 프론트 읽기 전용 대시보드 (~250줄)

## 5. 분기 일반화

`compile.py:596`의 현재 제약:

```python
_CONDITIONAL_ROUTING_TYPES = {"review.intent", "human.checkpoint", "loop.guard"}
```

노드가 사용자 정의로 자유로워지면 분기만 고정 3종에 묶어둘 수 없다. 판정 기준을
**타입 멤버십에서 그래프 구조로** 바꾼다:

> 라벨 달린 나가는 엣지를 둘 이상 가진 노드는 분기 노드다.

그런 노드는 출력 스키마에 `route: Literal[<라벨들>]` 필드가 자동으로 추가되고, LLM이
그중 하나를 고른 값으로 `add_conditional_edges`가 라우팅한다.
`_effective_output_schema(node, manifest)` (`compile.py:53`)가 이미 노드 인스턴스
설정에서 출력 스키마를 유도하므로 여기에 붙인다.

`human.checkpoint`/`loop.guard`는 LLM이 아니라 런타임이 라벨을 정하므로 현재 방식을
유지한다.

## 5.1 루프

루프는 **뒤로 가는 화살표 하나**다. `loop.reentry`는 삭제되고, 화살표 자체가
재진입이다.

### 가드 자동 삽입

무한 루프를 막는 예산(guard)이 필요하지만, 지금처럼 가드 없는 사이클을
`ValueError`로 거부하지 않는다. 뒤로 가는 화살표를 발견하면 파서가 기본 가드를
자동으로 끼운다(최대 3회, 소진 시 종말 노드로 탈출).

```yaml
flow: |
  input --> reasoning --> review
  review -->|ok|    output
  review -->|retry| reasoning     # 이것만으로 동작. 기본 3회.
```

내부적으로는 `Architecture` dict에 `__guard_1` 노드가 삽입된다. `arch.yaml`에도
mermaid 그림에도 나타나지 않으며, 그림에는 뒤로 가는 화살표에 `↻3` 배지만 붙는다.
대시보드는 `guard: 3 (기본값)`으로 표시해 숨기지 않는다.

**탈출 지점이 애매하면 에러다.** 나가는 엣지가 없는 노드가 둘 이상이면 자동으로
고르지 않고, 가드를 명시하라고 알린다.

예산을 직접 정하려면 가드를 이름 있는 노드로 꺼낸다. 그러면 소진 시 경로가 흐름에
드러난다:

```yaml
flow: |
  review -->|retry| retry3
  retry3 -->|계속|  reasoning
  retry3 -->|소진|  output

nodes:
  retry3: { run: loop.guard, max: 3 }   # 또는 maxTokens/maxCostUsd/maxDurationSec/stuck
```

가드 축 평가는 `server/nodes/loop_guard.py`의 5축 순수 함수를 그대로 쓴다.
`LoopRuntimeState`가 policy_id별 키를 갖는 병합 리듀서(`state.py:24`)라 중첩
루프도 그대로 동작한다.

### 회차 구분

같은 노드가 여러 번 방문되는 것을 그래프는 구분하지 않는다 — 노드는 하나다.
구분은 실행 기록에서 이뤄지며, 필요한 장치는 이미 있다:

- `workspace.py:43` `_seq_prefix` — 같은 node_id 재방문 시 시퀀스가 올라간다
  (`001-reasoning.md`, `004-reasoning.md`)
- `ExecutionEvent`에 `loop_runtime` 필드가 이미 있어 `iteration`이 WS로 나간다

대시보드는 `reasoning #1`, `reasoning #2`로 줄을 쌓아 보여주고, mermaid 그림은
노드 하나에 `#2` 배지만 붙인다. 그림은 구조지 기록이 아니다.

### 회차 간 상태 전달

같은 노드가 두 번 돌면 자기 출력을 덮어쓰므로, 2회차가 1회차와 달라지려면 앞
회차의 판단이 입력으로 들어와야 한다. 선택 입력(`?`)으로 명시한다:

```yaml
nodes:
  reasoning:
    in:  [task, plan, feedback?]     # 1회차엔 빈 값
    out: [answer]
    prompt: |
      계획을 따라 풀어라.

  review:
    in:  [task, answer]
    out: [verdict, feedback]         # 여기서 나온 feedback이 2회차 입력
```

무엇이 회차를 넘어 전달되는지가 파일에 드러나며, 자동 누적은 하지 않는다(토큰
증가가 통제 불가능해지므로).

## 6. 이미 열려 있는 seam

이 설계가 성립하는 것은 앞선 작업 덕이다.

- **Phase B② — `AgentState.vars`** (`state.py:71`): 병합 리듀서가 달린 자유 키
  버킷과 `read_state_value`/`write_state_value`(`state.py:79`, `:86`)가 있어,
  `in:`/`out:`에 어떤 이름을 써도 상태에 읽고 쓸 수 있다.
- **Phase B④ — `_effective_output_schema`** (`compile.py:53`): 매니페스트에
  `outputSchema`가 없으면 노드 인스턴스 설정에서 즉석 유도한다.
- **Phase A2 — 런타임 디스패치 정규화**: `compile.py`가 타입 문자열이 아니라
  `manifest["runtime"]` 기준으로 분기한다.

## 7. 브라우저 대시보드 (읽기 전용)

```
┌─────────────────────────────────────────┐
│  arch.yaml ▾    [입력...]      ▶ Run    │
├─────────────────────────────────────────┤
│    (mermaid 그림 — 실행 중 노드 색칠)     │
├─────────────────────────────────────────┤
│  ▸ planning   ✓ 1.2s                    │
│  ▾ reasoning  ▸ streaming...            │
│  · review     대기                       │
└─────────────────────────────────────────┘
```

- 그래프 **저작**이 읽기 전용이라는 뜻이다. 런타임 상호작용은 브라우저에서 한다.
- 노드 색칠은 mermaid `classDef`를 이벤트에 따라 붙였다 뗀다. 레이아웃 코드 없음.
- 체크포인트 도달 시 해당 노드 줄에 Approve/Revise/Reject 버튼이 나타난다
  (`CheckpointActions.tsx` + 기존 `resume` 메시지 재사용).
- 파일 저장 시 자동 갱신(파일 감시)은 후순위 항목. 없으면 새로고침.

## 8. 에러 처리

파서는 추측하지 않고 **줄 번호와 함께** 거부한다.

- `in:`에 적힌 이름을 선행 노드의 `out:`에서 찾을 수 없음
- `flow:`가 참조하는 노드가 `nodes:`에 정의되지 않음 (역도 마찬가지)
- 루프 탈출 지점이 애매함 (종말 노드가 둘 이상인데 가드가 명시되지 않음)
- 분기할 수 없는 노드(`human.checkpoint`/`loop.guard` 외 특수 노드)에 라벨 다수

경고(거부하지 않음):

- 서로 다른 두 노드가 같은 `out:` 이름을 씀 (§3.3)
- 가드 없는 사이클 — 지금 `compile_graph`가 던지는 `ValueError`를 줄 번호에 매핑

## 9. 테스트

`server/tests/test_archfile.py`:

- 스타터 그래프 왕복: yaml → dict → `compile_graph()` 성공
- mermaid 체인 분해: `a --> b --> c`가 엣지 2개로
- 라벨 파싱: 임의 문자열(한글 포함) 라벨이 그대로 보존됨
- §8 에러 4종에 줄 번호가 붙는지

- 가드 자동 삽입: 뒤로 가는 화살표만 있는 yaml이 `__guard_1`을 얻고, 종말 노드가
  둘이면 에러
- 중복 `out:` 이름에 경고가 나되 파싱은 성공하는지

분기 일반화는 `test_compile.py`에 추가: 라벨 엣지 2개를 가진 사용자 정의 노드가
`route` 필드를 얻고 조건부 라우팅으로 컴파일되는지.

## 10. 남은 결정

- 파일 감시 자동 갱신 여부 (후순위로 분류됨)
- `/api/node-types` CRUD (Phase B③, 현재 미배선) — 노드 타입 카탈로그 자체가
  사라지므로 이번 전환에서 삭제 후보
