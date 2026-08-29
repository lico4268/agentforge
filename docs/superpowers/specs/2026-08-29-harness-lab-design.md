# Harness Lab — 설계 문서

> ✅ **현재 진행 중** — 2026-08-29 브레인스토밍 결과.
> agentforge 저장소에 기록하되, **구현은 새 저장소**에서 한다(§0.3).
> `DIRECTION.md`와의 관계는 §0.4 참고.

---

## 0. 무엇을 만드는가

### 0.1 한 문장

**에이전트 하네스를 조립하고 관찰하는 UI.** 하네스 자체를 새로 만드는 게 아니라,
이미 있는 하네스(Pi)를 해부해서 설정과 루프를 눈에 보이게 하고 손대게 한다.

### 0.2 동기

Claude Code·Codex 같은 하네스는 설정과 루프가 감춰져 있다. 컨텍스트에 무엇이
실려 나가는지, 컴팩션이 언제 무엇을 지웠는지, 어떤 규칙으로 툴이 차단되는지
사용자가 볼 수 없다. 이 프로젝트는 그 표면을 전부 드러낸다.

관측 대상은 장난감이 아니라 **실물 하네스(Pi coding agent)** 다. 실제로 감춰져 있던
것을 보는 게 목적이므로 대상이 실물이어야 의미가 있다.

### 0.3 확정된 전제

| 항목 | 결정 |
|---|---|
| 용도 | **랩 먼저**, 실사용 드라이버는 나중 |
| 저장소 | **새 저장소** — agentforge는 현 궤도 유지 |
| 언어/런타임 | **TypeScript / Node** (Python·LangGraph 백엔드 안 가져감) |
| 에이전트 런타임 | **`pi-coding-agent`의 `createAgentSession()`** — 필요해지면 포크(MIT) |
| 캔버스 노드 | **Pi의 훅 지점 7개, 고정** |
| 캔버스 형태 | **순환 다이어그램** (루프를 루프로 그림) |

### 0.4 DIRECTION.md와의 관계

`DIRECTION.md` §1은 "LLM 에이전트 아키텍처를 그리고 그 자리에서 실행하는 캔버스"
라고만 말하고 **무엇을 그리는지**는 열려 있었다. 이 문서가 그 답이다:

> 그리는 대상 = **하네스의 구성**. 캔버스가 하는 일 = **조립 + 관찰**.

`DIRECTION.md` §2("노드 역할을 우리가 고정하지 않는다")와 같은 뿌리다 — 하네스가
감춘 것을 우리도 감추지 않는다.

단, 이 프로젝트에서는 노드가 **7개로 고정**된다. §2와 모순처럼 보이지만 아니다:
노드 개수를 우리가 정하는 게 아니라 **Pi가 뚫어둔 훅이 그게 전부**이기 때문이다.
캔버스가 "개조 가능한 표면이 여기까지"라고 말해주는 것 자체가 정보다.

---

## 1. 시스템 구조

### 1.1 프로세스

```
┌─ browser (Vite) ────────────┐            ┌─ node ────────────────────────┐
│  Canvas: 순환 다이어그램      │            │  server.ts                    │
│  Inspector: 부품 편집         │◄─── ws ───►│   ├ ws 서버                    │
│  RawEventLog: 날것 이벤트     │            │   ├ createAgentSession()      │
│  useHarnessStore             │            │   ├ labExtension(cfg)         │
│  useEventStore               │            │   └ harnesses/*.json          │
│  useProjectionStore          │            │      runs/*.jsonl             │
└─────────────────────────────┘            └───────────────────────────────┘
                                                    API 키는 여기에만
```

브라우저에서 직접 돌지 않는 이유: ① 툴이 fs/셸을 만짐 ② API 키가 브라우저 번들에
들어가면 안 됨 ③ 나중에 헤드리스 실행으로 승격하려면 어차피 필요.

### 1.2 백엔드 구성

```
server/
  server.ts        ~80줄   ws 서버 + 세션 생성 + 이벤트 릴레이 + JSONL 기록
  labExtension.ts  ~120줄  HarnessConfig를 각 훅에서 해석하는 범용 확장
  rules.ts         ~80줄   applyRules / matchGate / truncate (순수 함수)
  harness.ts       ~40줄   harnesses/*.json 로드·저장
```

의존성 3개: `@earendil-works/pi-coding-agent`(스코프는 설치 시 `npm view`로 확정 —
문서마다 `@mariozechner/`와 갈림), `ws`, `zod`. (커스텀 툴 등록은 v2이므로 `typebox`는
지금 넣지 않는다.)
**웹 프레임워크 없음** — REST 엔드포인트가 필요 없다.

### 1.3 WS 프로토콜

```ts
// client → server
{ kind: 'run', harness: HarnessConfig, prompt: string }
{ kind: 'stop' }
{ kind: 'save', name: string, harness: HarnessConfig }

// server → client
{ kind: 'event', sessionId: string, parentSessionId: string | null, event: <Pi 원본> }
{ kind: 'error', message: string }
```

`run`에 설정 **전체**를 싣는다. 서버는 하네스를 기억하지 않는다 — 캔버스에 보이는
것이 곧 실행되는 것. 이 성질이 v3에서 이 실행을 LangGraph 노드 본문으로 그대로
뜯어 쓸 수 있게 한다.

`sessionId`/`parentSessionId`는 **v1에서 상수와 null이지만 지금 넣는다.** v2에서
서브에이전트 이벤트가 같은 스트림으로 쏟아질 때 이 두 필드가 없으면 스토어와
투영을 전부 다시 짜야 한다.

### 1.4 "날것 이벤트" 원칙

**하지 않는 것 — 가공/요약.** Pi 이벤트의 필드를 골라내거나 이름을 바꾸거나 합치지
않는다. Zod는 `.passthrough()`로 검증만 하고 모르는 필드도 통과시킨다. 원본 객체를
그대로 배열에 쌓고 `RawEventLog`에서 언제든 펼쳐본다.

**하는 것 — 투영.** 어느 노드를 켤지는 파생 함수가 정한다(§3.3). 투영은 단방향이고
손실이 있어도 된다 — 원본이 항상 옆에 남아 있으므로.

### 1.5 agentforge에서 가져오는 것

| 자산 | 판정 |
|---|---|
| `Canvas.tsx`, `AgentNode`, `AgentEdge`, `radialLayout.ts` | 그대로 재사용 |
| `Inspector.tsx`의 `PortListEditor` +/- 패턴 | 패턴만 이식 → 툴/규칙 목록 편집기 |
| `loopProjection.ts` | 사고방식만 (원본 → 뷰 투영) |
| `useExecutionStore` 형태 | 형태만 (순수 fold + 노드별 셀렉터) |
| `eventReducer.ts` | ❌ 못 씀 — `node_start`/`policyDecision` 전제, 상태 기계가 다름 |
| `types/events.ts`, `builtinManifests`, 매니페스트 레지스트리 | ❌ 폐기 (노드 7개 고정이라 레지스트리 불필요) |
| Python 전부 | ❌ |

---

## 2. 캔버스 모델

### 2.1 노드 = Pi의 훅 지점 (7개, 고정)

```
        ┌─────────────────────────────────────────────┐
        │                                             │
  [입력]─┤  [컨텍스트]→[모델]→[툴 게이트]→[툴 실행]→[결과]├─┐
   ✏️   │      ✏️★     👁⚙️     🛑        👁⚙️     ✏️  │ │
        │       ▲                                    │ │
        └───────┴────────────────────────────────────┘ │
                │                                      │
           [컴팩션]✏️🛑                            [종료]👁
```

사이클 = `컨텍스트 → 모델 → 툴게이트 → 툴실행 → 결과 → 컨텍스트`, 한 바퀴 = 1 turn.
`입력`은 진입점(실행당 1회), `종료`는 이탈점, `컴팩션`은 조건부 곁가지.

배지: ✏️ 변형 가능 · 🛑 차단 가능 · 👁 관측 전용 · ⚙️ 설정값 있음

### 2.2 노드별 역할

| # | 노드 | 훅 | 발화 | 역할 |
|---|---|---|---|---|
| 1 | 입력 | `before_agent_start` | 실행당 1회 | 시스템 프롬프트 교체·메시지 주입. **코딩 전용 프롬프트를 벗기는 지점** |
| 2 | 컨텍스트 ★ | `context` | **턴마다** | 모델에 전송될 messages 전체를 가로채 변형. 토큰 누수의 관측·처방 지점. **라우팅/서브에이전트/plan mode가 전부 여기서 만들어진다** |
| 3 | 모델 | 없음(관측) | 턴마다 | 스트리밍·토큰·지연. **Pi도 못 뚫는 진짜 블랙박스 — 바꿀 수 있는 척하지 않는다** |
| 4 | 툴 게이트 | `tool_call` | 툴 호출마다 | 실행 전 차단 + 사유(모델에게 결과로 전달됨) |
| 5 | 툴 실행 | 없음(세션 설정) | 툴 호출마다 | 빌트인 8종 선택 / `noTools:all`. **범용화 스위치** |
| 6 | 결과 | `tool_result` | 툴 호출마다 | 모델이 보기 전 결과 변형. 토큰 상류 처방 |
| 7 | 컴팩션 | `session_before_compact` | 조건부 | 막거나 요약을 직접 써넣음. **무엇이 조용히 사라지는가** |

노드 수를 늘리거나 줄이지 못한다 — Pi의 훅이 이게 전부다.

### 2.3 노드별 편집 항목 (v1)

| 노드 | 편집 | 실행 중 표시 |
|---|---|---|
| 입력 | 시스템 프롬프트(기본값은 Pi 원본을 채워 보여줌), 주입 메시지 | 프롬프트 토큰 수 |
| 컨텍스트 | 규칙 +/-: `최근 N턴 유지` · `이 툴 결과 제외` · `프리픽스 주입` | 전송 메시지 수/토큰, 규칙 적용 전후 차이 |
| 모델 | provider·model, `thinkingLevel` | 스트리밍 텍스트, 입출력 토큰, 지연 |
| 툴 게이트 | 차단 규칙 +/-: `툴명 + 인자 패턴 → 차단(사유)` | 호출된 툴, 차단 건수 |
| 툴 실행 | 빌트인 8종 체크박스, `noTools:all` | 실행 중 툴, 소요 |
| 결과 | 최대 길이 자르기 | 원본/변형 후 크기 |
| 컴팩션 | on/off, 임계값, 요약 프롬프트 | 발화 여부, 전후 토큰 |

**v1에서 뺀 것**: 커스텀 툴 등록, 서브에이전트, 조건부 라우팅, 세션 브랜칭,
하네스 비교. 전부 `context`/`registerTool` 위에 얹히므로 노드 추가 없이 확장된다.

### 2.4 설정 → 동작 (코드 생성 안 함)

```ts
type HarnessConfig = {
  systemPrompt: string | null        // null = Pi 기본값
  injectMessage: string | null
  contextRules: ContextRule[]        // discriminated union — 종류 추가로 확장
  model: { provider: string; id: string; thinkingLevel: 'off'|'low'|'medium'|'high' }
  toolGate: GateRule[]
  tools: string[] | 'none'
  resultMaxChars: number | null
  compaction: { enabled: boolean; thresholdTokens: number; prompt: string | null }
}
```

범용 확장 `labExtension(cfg)` 하나가 이 JSON을 각 훅에서 해석한다. 규칙이 늘어도
확장 코드가 늘지 않고 `switch` 분기만 는다.

```ts
const labExtension = (cfg: HarnessConfig) => (pi) => {
  pi.on('before_agent_start', e => ({
    systemPrompt: cfg.systemPrompt ?? e.systemPrompt,
    message: cfg.injectMessage ? { content: cfg.injectMessage, display: true } : undefined,
  }))
  pi.on('context',  e => ({ messages: applyRules(cfg.contextRules, e.messages) }))
  pi.on('tool_call',   e => matchGate(cfg.toolGate, e) ?? undefined)
  pi.on('tool_result', e => cfg.resultMaxChars ? truncate(e, cfg.resultMaxChars) : undefined)
  pi.on('session_before_compact', e => compactionDecision(cfg.compaction, e))
}
```

### 2.5 코드를 보여준다 (읽기 전용)

각 노드 Inspector 하단에 "이 설정이 실행하는 코드" 접이식 패널 — 위 훅 핸들러의
해당 부분을 읽기 전용 렌더. 코드젠 왕복(코드 편집 → 파싱 → 캔버스 반영)의 복잡도
없이 투명성만 얻는다. 필요해지면 나중에 편집 가능하게 연다.

---

## 3. 데이터 흐름과 상태 관리

### 3.1 문제

이벤트가 두 종류로 성질이 다르다. `tool_call`은 툴당 1번(세션에 수백 개),
`message_update`는 **토큰마다 1번**(응답당 수천 개). 같은 통에 넣고 같은 방식으로
처리하면 UI가 죽는다. 이 절은 사실상 이 하나의 문제를 푼다.

### 3.2 스토어 3분할

| 스토어 | 내용 | 갱신 빈도 | 구독자 |
|---|---|---|---|
| `useHarnessStore` | `HarnessConfig` | 타이핑할 때만 | Inspector, 노드 배지 |
| `useEventStore` | **원본 이벤트 append-only** | 초당 수백 | **RawEventLog 하나만** |
| `useProjectionStore` | 노드별 파생 런타임 | 초당 ~10 (스로틀) | 캔버스 노드 7개 |

합치면 안 되는 이유: 하나로 두면 타이핑 한 글자가 캔버스 7노드를 전부 리렌더하고,
반대로 스트리밍 토큰이 Inspector 폼을 리렌더해 포커스가 튄다. 초당 수백 번 바뀌는
창고를 **딱 하나의 화면만** 구독하게 하는 것이 핵심.

### 3.3 투영 (projection)

이벤트에는 "어느 노드를 켜라"는 정보가 없다(Pi는 우리 캔버스를 모른다). 파생 함수가
정한다.

```ts
function project(events: RawEvent[]): Record<NodeId, NodeRuntime>
```

| 이벤트 | 노드 | 기록 |
|---|---|---|
| `before_agent_start` | 입력 | active, 프롬프트 토큰 |
| `agent_start` | — | 실행 시작, 턴 0 |
| `turn_start` | — | **턴 +1** |
| `context` | 컨텍스트 | active, 메시지 수·토큰, 규칙 전후 차이 |
| `message_start/update/end` | 모델 | active, 스트리밍, 입출력 토큰, 지연 |
| `tool_call` | 툴 게이트 | active, 툴명·인자, 차단 여부 |
| `tool_execution_*` | 툴 실행 | active, 툴명, 소요 |
| `tool_result` | 결과 | active, 원본/변형 후 크기 |
| `session_before_compact` | 컴팩션 | 발화, 전후 토큰 |
| `agent_end` | 종료 | 총 턴·토큰·비용·시간 |

**성질 1 — 순수 함수.** 같은 입력이면 항상 같은 출력. 그래서 **리플레이가 공짜다**:
저장된 이벤트를 처음부터 다시 먹이면 실행이 재생되고, 앞부분만 잘라 먹이면 그 시점
화면이 나온다(타임트래블). 리플레이 기능을 따로 만들지 않는다.

**성질 2 — 손실 허용.** 요약해도 된다. 원본이 `useEventStore`에 온전히 남아 있고
노드 클릭으로 꺼내 본다. 다른 하네스가 답답한 이유가 정확히 "요약만 주고 원본을
안 주는 것"이므로 이 구조가 프로젝트의 정체성이다.

### 3.4 스트리밍 볼륨 대책 (v1 필수)

agentforge의 현행 패턴 `events: [...s.events, event]`는 이벤트마다 배열 전체를
복사해 총비용이 O(n²)다. 20개면 무시할 만하지만 20,000개면 브라우저가 멈춘다.

| 대책 | 내용 | v1 |
|---|---|---|
| ① append + 버전 카운터 | 원본은 `events.push()` (O(1)), 화면은 `version` 숫자만 구독 | **필수** |
| ② 스트리밍 우회 | `message_update` 델타는 스토어를 안 거치고 노드의 ref에 이어붙이고 `requestAnimationFrame`으로 프레임당 1회 렌더 (340회 → 최대 6회) | **필수** |
| ③ 투영 스로틀 | 노드 숫자 갱신은 초당 10회 | **필수** |

①②는 스토어 구조와 컴포넌트 설계를 좌우하는 구조적 결정이라 처음에 정해야 하고,
③은 순수 함수에 래퍼 하나라 나중에 붙여도 되지만 함께 넣기로 확정.

원본 델타는 ①의 배열에 전부 들어간다(로그에서 볼 수 있어야 하므로). React의 불변성
관례를 깨는 지점이지만, append만 하고 기존 원소를 수정하지 않으므로 안전하다.

### 3.5 영속

- **하네스 설정**: `harnesses/<name>.json`. `save` 메시지로 서버가 씀. DB 없음.
  v2/v3에서 "에이전트 타입 정의"로 그대로 재사용된다.
- **실행 기록**: `runs/<runId>.jsonl` — 이벤트를 받는 족족 한 줄씩 append.
  중간에 끊겨도 앞부분이 온전하다(배열 JSON은 닫는 괄호가 없으면 전체가 깨짐).
  §3.3의 순수성 덕에 이 파일만 있으면 실행이 그대로 재생된다.

Pi 자신의 세션 JSONL과는 별개다 — 그건 대화 기록, 이건 훅 관점의 관측 기록.

---

## 4. 에러 처리와 테스트

### 4.1 원칙

랩에서 **에러는 숨길 대상이 아니라 관측 대상**이다. 에러도 이벤트로 원본 그대로
쌓이고, 해당 노드가 빨갛게 되고, 클릭하면 스택트레이스까지 보인다. 삼키지 않는다.

### 4.2 실패 종류별

| 종류 | 처리 |
|---|---|
| **툴 실패** (`isError: true`) | **에러 아님 — 정상 흐름.** 모델에게 전달되고 모델이 대응. `결과` 노드에 ⚠️만 |
| **툴 차단** (게이트 규칙) | 정상 흐름. 차단 카운트 +1, 사유 표시 |
| **모델 API 에러** (401·rate limit·컨텍스트 초과) | `{kind:'error'}` 전송, `모델` 노드 빨강 + 원문. **실행 중단** |
| **설정 오류** | Zod 검증 → 실행 시작 안 함. 문제 필드를 Inspector에서 빨갛게. 서버까지 안 감 |
| **WS 끊김** | §4.3 |
| **확장 훅 자체가 터짐** | 훅마다 try/catch. **그 훅만 무시하고 원본 통과** + 에러 이벤트 발행. 캔버스에 크게 표시. 컨텍스트 규칙 하나의 버그로 세션 전체가 죽으면 실험을 못 하므로 |

### 4.3 WS 끊김 (v1)

- 재연결은 지수 백오프, 상단 배너 표시
- **진행 중이던 실행은 포기 — 재개(resume) 없음**
- 이미 받은 이벤트는 유지(원본 배열 + `runs/*.jsonl`). 화면은 끊긴 시점 상태로 남음

재개를 v1에서 빼는 이유: 서버가 상태를 안 들고 있기로 했으므로(§1.3) 재개하려면
세션 레지스트리가 필요하다. **v2에서 서브에이전트 때문에 어차피 필요해지므로 그때
함께 구현한다** (§5 로드맵에 명시).

### 4.4 테스트

어려운 부분이 전부 순수 함수라 테스트가 쉽다. **API 키가 필요한 것은 수동 검증
하나뿐이고, 자동 테스트는 전부 네트워크·비용 0이다.**

**단위 테스트 (여기에 힘을 준다, TDD)**

| 대상 | 내용 |
|---|---|
| `project(events)` | 픽스처 JSONL → 기대 노드 상태. **가장 중요.** Pi가 이벤트 형식을 바꾸면 여기가 먼저 깨져 알려준다 |
| `applyRules(rules, messages)` | 최근 N턴 유지 / 툴 결과 제외 / 프리픽스 주입 |
| `matchGate(rules, toolCall)` | 패턴 매칭 경계 케이스 |
| `truncate(result, max)` | 자르기 |
| `HarnessConfigSchema` | 잘못된 설정이 통과하지 않는지 |

**서버 테스트** — `createAgentSession`을 진짜로 부르지 않고 가짜 세션 객체를 주입한다.

```ts
const fakeSession = { subscribe: (fn) => { /* 준비된 이벤트를 순서대로 먹임 */ } }
```

검사 항목: 이벤트가 WS로 원본 그대로 릴레이되는가, `sessionId`가 붙는가, JSONL에
기록되는가, 훅 예외가 세션을 죽이지 않는가.

> **API 키 없이 도는 것이 요구사항이다.** agentforge는 `ANTHROPIC_API_KEY` 401로
> E2E가 수개월 막혀 있었다. 실행 경로 대부분이 키 없이 검증되어야 그 실수를
> 반복하지 않는다.

**성능 회귀 테스트** — 가짜 이벤트 20,000개를 메모리에서 만들어 `project()`에 먹이고
소요 시간을 임계값(2초)과 비교. 네트워크·모델 호출 없음 = **비용 0**, CI에서 돎.
누가 무심코 배열 복사를 다시 넣으면 이 테스트가 잡는다.

**수동 검증 (자동화 안 함)** — 캔버스 시각 확인, 스트리밍 매끄러움, 실제 API로 한
세션. 샌드박스에 헤드리스 브라우저가 없으므로(agentforge와 동일 제약) 사용자가
`npm run dev`로 확인한다. 그래서 더더욱 순수 함수 테스트에 힘을 준다.

---

## 5. 로드맵 — 확장성 검증 결과

브레인스토밍 중 "오케스트레이션·복잡한 루프·그래프 엔지니어링으로 확장되는가"를
실제 사례로 검증했다. 결론: **확장되고, v1에서 추가로 해둘 일은 §1.3의 두 필드뿐.**

### 5.1 층이 둘이다

```
바깥 층: 오케스트레이션        ← 노드 = 에이전트 하나
   [플래너]──▶[구현자]──▶[리뷰어]
      └────▶[스카우트](병렬)
                │ drill-down
                ▼
안쪽 층: 하네스 분해도          ← 노드 = 훅 지점 7개
   [입력]→[컨텍스트]→[모델]→[게이트]→[툴]→[결과] ⟲ [컴팩션]
```

바깥 층은 **agentforge가 이미 만든 캔버스**(노드=에이전트, 엣지=위임)다. 버리는 게
아니라 한 층 위로 올라가고, 그 아래에 없던 안쪽 층이 새로 생긴다.

### 5.2 검증 근거

Pi 코어를 고치지 않고 **확장만으로** 멀티에이전트를 구현한 프로젝트가 최소 5개:
`tintinweb/pi-subagents`(병렬 풀·fleet view·커스텀 에이전트 타입·실행 중 스티어링·
중첩 depth cap), `0xKobold/pi-orchestration`(single/chain/parallel/fork),
`ruizrica/agent-pi`(6패턴), `tmdgusya/roach-pi`, `nicobailon/pi-subagents`.

메커니즘: 새 훅이 필요 없다. `pi.registerTool()`로 `agent` 툴을 등록하고 그것이
**자식 세션을 띄운다**(별도 프로세스 또는 in-process `createAgentSession()`).

### 5.3 알려진 한계

Pi의 한 세션은 **선형 대화 + 툴 루프**다. 한 세션 *안에서* 병렬 브랜치가 갈라졌다
합쳐지는 진짜 DAG는 불가능하다. 분기·병렬·합류는 **자식 세션을 띄우는 방식**으로만
표현된다. 즉 그래프 엔지니어링 = **세션들의 그래프**이지 세션 내부의 그래프가 아니다.
포크해도 마찬가지다(대화라는 자료구조가 선형이므로). 이 한계는 v3에서 해소된다.

### 5.4 LangGraph는 바깥에 붙인다

`@langchain/langgraph`(TS)는 2026 현재 Python과 사실상 기능 동등하다(StateGraph,
`addConditionalEdges`, 체크포인터, 스트리밍, human-in-the-loop). Node 백엔드로
정한 결정이 여기서 보상받는다.

- ❌ **안쪽에 넣지 않는다** — Pi 루프를 LangGraph로 대체하면 확장·훅·컴팩션·세션이
  전부 죽는다. 둘 다 루프를 소유하는 물건이라 겹치면 하나가 죽는다.
- ✅ **바깥에 붙인다** — LangGraph 노드 하나 = Pi 세션 하나. 노드는 `(state)=>newState`
  함수이므로 그 안에서 `createAgentSession()`을 돌리고 결과를 상태에 쓰면 된다.

이러면 §5.3의 한계가 해소된다: `Send()` 팬아웃/팬인, 1급 조건부 분기, 상태 채널과
리듀서, 체크포인터 기반 타임트래블, `interrupt()` 기반 사람 개입.

agentforge `compile.py`(787줄)에서 얻은 "캔버스 그래프 → StateGraph 컴파일" 경험이
그대로 옮겨온다(langgraph.js API가 동일). 차이는 잎노드가 단발 LLM 호출이 아니라
**툴을 쥔 진짜 하네스**라는 것.

**지금 붙이지 않는 이유**: ① v1은 바깥 층을 만들지 않음 ② 상태 모델이 강한 의견을
가져 일찍 넣으면 안쪽 설계까지 끌려감 ③ 하네스 하나가 제대로 돌기 전엔 무엇을
오케스트레이션할지 알 수 없음.

**v1이 막지 않음이 확인됨**: 필요 조건 두 개가 이미 충족된다 — Pi 실행이 순수 함수
`(HarnessConfig, input) → result`(§1.3), 이벤트에 세션 구분자(§1.3).

### 5.5 단계

| | 만드는 것 | 캔버스 의미 | 함께 들어가는 것 |
|---|---|---|---|
| **v1** | 하네스 하나 조립 + 관찰 | 훅 7노드 순환도 | — |
| **v2** | 서브에이전트 (Pi 확장 방식) | 세션 트리 drill-down | **세션 레지스트리 → WS 재개(§4.3)**, 커스텀 툴 등록 |
| **v3** | LangGraph 오케스트레이션 | 진짜 DAG, 노드=하네스 | 체크포인터 기반 타임트래블 |

v3이 원래 agentforge가 하려던 것이고, v1·v2가 그 밑에 없던 층을 까는 것이다.

---

## 6. 참고

- Pi: https://pi.dev/ · https://github.com/earendil-works/pi (MIT)
- SDK: `createAgentSession()` — `tools`/`excludeTools`/`noTools`, `systemPromptOverride`,
  `model`/`thinkingLevel`/`scopedModels`, `extensionFactories`, `session.subscribe`
- 확장 훅 등급: 변형(`before_agent_start`, `context`, `tool_result`,
  `session_before_compact`) / 차단(`tool_call`, `session_before_compact`,
  `session_before_switch`) / 관측(나머지)
- 빌트인 툴 팩토리: `createReadTool` `createWriteTool` `createEditTool` `createBashTool`
  `createGrepTool` `createFindTool` `createLsTool` (동명 등록으로 덮어쓰기 가능)
- 오케스트레이션 선례: tintinweb/pi-subagents, 0xKobold/pi-orchestration,
  ruizrica/agent-pi, tmdgusya/roach-pi, nicobailon/pi-subagents
- LangGraph TS: `@langchain/langgraph`
