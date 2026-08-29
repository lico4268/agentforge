# 현재 방향 (source of truth)

> 최종 갱신: 2026-08-28. **이 문서가 다른 모든 설계 문서보다 우선한다.**
> 여기와 충돌하는 내용이 다른 문서에 있으면 그 문서가 낡은 것이다.

## 1. 우리가 만드는 것

**LLM 에이전트 아키텍처를 그리고, 그 자리에서 실행·테스트하는 캔버스.**
정적 다이어그램 도구가 아니고(참고: archify), 범용 시스템 아키텍처 툴도 아니다.
그리는 대상은 LLM 에이전트 파이프라인이고, 그린 것은 그대로 실행된다.

## 2. 노드의 역할을 우리가 고정하지 않는다

- 노드 타입에 "리뷰어" "플래너" 같은 **역할을 못 박지 않는다.** 역할은 사용자가
  이름·시스템 프롬프트·입출력 포트로 정한다 (`custom.node`, Inspector 편집).
- 분기 이름(`accept`/`refine`/`clarify`, `approve`/`revise`/`reject`)은 **예시일 뿐
  계약이 아니다.** 사용자가 원하는 개수·이름으로 분기를 만들 수 있어야 한다.
- 우리가 제공하는 것은 **스위치라는 장치**지 스위치의 의미가 아니다.

## 3. 스위치 노드가 갖는 유일한 우리 쪽 개념: 판정 주체

분기 노드에 대해 시스템이 아는 것은 하나뿐이다 — **누가 고르는가.**

| `decidedBy` | 동작 |
|-------------|------|
| `llm`       | 선언된 분기 이름 중 하나를 LLM이 고른다 |
| `human`     | interrupt 걸고 사람이 분기 버튼으로 고른다 |

`review.intent`(LLM 판정)와 `human.checkpoint`(사람 판정)는 **같은 노드의 두
설정값**으로 수렴한다. 별개 타입 + 별개 처리 경로로 유지하지 않는다.

## 4. 캔버스 시각 문법

- 분기 여부는 **이름이 아니라 출력 포트 개수**로 판정한다. 이름 화이트리스트 금지.
- 엣지 색은 분기 **인덱스**로 팔레트에서 배정한다. 의미는 라벨이 진다
  (accept라서 초록이 아니라, 첫째 분기라서 초록).
- 노드에서 나가는 선은 기본 하나. 여러 개는 분기일 때만.
- 판정 주체는 노드 배지 하나로 표시한다 (LLM / 사람).

## 5. 알려진 낡은 코드 (고칠 대상)

- `ui/src/canvas/edges/edgePresentation.ts` — 분기 이름 화이트리스트
- `server/nodes/policy.py` — `ReviewBranch = Literal["accept","refine","clarify"]`
- `server/manifests.py` / `ui/src/registry/builtinManifests.ts` — `review.intent`의
  고정 출력 포트 3개
- `server/nodes/review.py` — 프롬프트가 위 어휘로 쓰여 있음
- `server/harness.py` — 지표가 분기 이름을 세고 있음 (`refine_rate`/`clarify_rate`)
- `ui/src/canvas/edges/AgentEdge.tsx` — 선이 target 중심까지 그려져 화살촉이
  노드 원 안에 묻힘(방향이 안 보이는 실제 버그)

## 6. 문서 취급 규칙 (배너 4종)

각 문서 첫 줄 배너가 어떻게 읽어야 하는지 말해준다.

| 배너 | 대상 | 어떻게 읽나 |
|---|---|---|
| 📄 **완료된 작업 기록** | `docs/superpowers/plans/*`, `work/**` | 이미 한 일의 로그. 설계로 받아들이지 않는다 |
| 📚 **낡은 설계 / 조사 기록** | `docs/superpowers/specs/*`, `POLICY_RESEARCH.md` | 당시 판단 근거를 찾을 때만 |
| ✅ **현재 진행 중** | `specs/2026-08-16-freeform-connections-node-templates-design.md` | 유효. 단 분기 관련 서술은 이 문서가 우선 |
| 배너 없음 | `CLAUDE.md`, `ROADMAP.md`, `backend-architecture.md`, `POLICY_REDESIGN.md` | 현행 문서. 목표 설계는 여전히 이 문서가 우선 |

- `POLICY_REDESIGN.md` §0에 무엇이 무효가 됐는지 표로 정리해뒀다.
- `refer_data/docs/**` — 초기 기획서, 읽기 전용. 2~4절과 충돌하는 부분은 무효.
- 백업은 git이 한다. 문서 사본을 따로 남기지 않는다.
