# AgentForge

`arch.yaml`로 LLM 에이전트 파이프라인을 정의하고, 브라우저에서 구조와 실행 과정을
확인하는 로컬 개발 도구입니다. YAML의 `flow`를 Mermaid 다이어그램으로 표시하고,
같은 정의를 LangGraph `StateGraph`로 컴파일해 실행합니다.

> 현재 개발 단계: **v0.5 — 텍스트 우선 아키텍처 전환 완료**

## 주요 기능

- 텍스트 기반 에이전트 정의: `server/arch/*.yaml`
- Mermaid 기반 읽기 전용 실행 다이어그램
- YAML 아키텍처를 LangGraph 그래프로 동적 컴파일
- LLM 또는 사람 판단에 따른 조건 분기
- 피드백 루프 자동 감지 및 `loop.guard` 삽입
- WebSocket 기반 실시간 노드 상태·로그·결과 전송
- Human Checkpoint 일시정지 및 승인·수정·거절 후 재개
- 노드 출력의 Markdown 저장 및 조회
- OpenRouter 모델 카탈로그와 즐겨찾기 지원

## 빠른 시작

### 요구 사항

- Python 3.12
- Node.js와 npm
- [`uv`](https://docs.astral.sh/uv/)

### 실행

```bash
git clone <repository-url>
cd agentforge
./start.sh
```

첫 실행 시 백엔드 가상환경과 프론트엔드 의존성을 준비합니다. 생성된
`server/.env`에 사용할 모델의 API 키를 설정한 뒤 다시 실행하세요.

```dotenv
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
```

필요한 키만 설정하면 됩니다. 사용 가능한 모델과 기본 모델은 `config.yaml`에서
관리합니다.

| 서비스 | 주소 |
|---|---|
| 프론트엔드 | http://localhost:5137 |
| 백엔드 | http://localhost:8000 |
| API 문서 | http://localhost:8000/docs |

`start.sh`는 두 개발 서버를 함께 실행하며 `Ctrl+C`로 모두 종료합니다. 프론트엔드는
LAN에도 공개되므로 같은 네트워크의 다른 기기에서 VM 주소의 `5137` 포트로 접속할 수
있습니다.

## 아키텍처 작성

`server/arch/` 아래에 `.yaml` 파일을 추가합니다. 브라우저를 새로고침하면 목록에
나타납니다.

```yaml
name: GSM8K Treatment
model: google/gemini-3.1-flash-lite

flow: |
  input --> planning --> reasoning --> review
  review -->|ok| output
  review -->|retry| reasoning

nodes:
  planning:
    in: [task]
    out: [plan]
    prompt: |
      문제를 풀 단계로 쪼개라. 각 단계 한 줄씩.

  reasoning:
    in: [task, plan, feedback]
    out: [answer]
    prompt: |
      계획을 따라 풀어라. 마지막 줄에 답만 숫자로 써라.

  review:
    in: [task, answer]
    out: [feedback]
    prompt: |
      답이 문제에 맞는지 확인해라. 맞으면 ok, 틀리면 retry로 보내고
      feedback에 무엇이 틀렸는지 써라.
```

`flow`가 실행 순서와 분기를 정의하고, `nodes`가 각 LLM 단계의 입출력과 프롬프트를
정의합니다. 출력 라벨이 여러 개인 노드는 분기 노드로 처리됩니다. 되돌아가는 엣지는
루프로 인식되어 실행 한도를 관리하는 guard가 자동으로 추가됩니다. 파싱 오류는 원본
YAML의 줄 번호와 함께 대시보드에 표시됩니다.

## 동작 구조

```text
server/arch/*.yaml
        │
        ▼
 archfile.parse_arch ──► Mermaid 읽기 전용 다이어그램
        │
        ▼
 graphs.compile_graph
        │
        ▼
 LangGraph StateGraph ──WebSocket──► 실행 상태·로그·결과
```

백엔드는 `FastAPI`, `LangGraph`, `Pydantic`을 사용하고 프론트엔드는 `React`,
`TypeScript`, `Vite`, `Zod`로 구성되어 있습니다.

## 개발 명령

백엔드:

```bash
cd server
.venv/bin/ruff check .
.venv/bin/ruff format .
.venv/bin/pytest
```

프론트엔드:

```bash
cd ui
npm run lint
npm run build
npm run test
```

## 주요 디렉터리

```text
server/
├── arch/              # 사용자가 작성하는 arch.yaml
├── archfile.py        # YAML·Mermaid flow 파서
├── graphs/compile.py  # 동적 LangGraph 컴파일러
├── nodes/             # 노드 실행 헬퍼
├── workspace.py       # 실행 결과 파일 저장소
└── main.py            # FastAPI와 WebSocket 진입점

ui/src/
├── app/               # 대시보드, 다이어그램, 진행 목록
├── execution/         # 실행 상태 관리
├── transport/         # WebSocket과 mock transport
├── registry/          # REST API 클라이언트
└── types/             # Zod 기반 API 계약
```

## 현재 범위와 다음 단계

텍스트 기반 작성, 동적 실행, 조건 분기, 루프, Human Checkpoint까지 구현되어 있습니다.
현재 주요 후속 작업은 임의 노드 조합의 완전한 일반화, 고정 정책 어휘 제거,
아키텍처 저장·불러오기 UI, 대규모 GSM8K 검증과 τ²-bench 연동입니다.

자세한 현재 상태는 [ROADMAP.md](./ROADMAP.md), 설계 원칙은
[DIRECTION.md](./DIRECTION.md), 개발 규칙은 [AGENTS.md](./AGENTS.md)를 참고하세요.
