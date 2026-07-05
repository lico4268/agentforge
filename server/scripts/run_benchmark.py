"""
GSM8K 소액 벤치마크 진입점 스크립트.

JSONL(items) 로드 → 모델 빌드 → arch별 그래프 실행 → 표 출력 + 결과 JSON 저장.
사용 예 (server/ 디렉토리에서):
    .venv/bin/python scripts/run_benchmark.py --arch both --limit 10
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# server/ 디렉토리를 패스에 추가 — 프로젝트 모듈 import 전에 수행
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphs.baseline import build_baseline  # noqa: E402
from graphs.treatment import build_treatment  # noqa: E402
from harness import Item, Report, run_dataset  # noqa: E402
from models import build_model  # noqa: E402


def load_items(path: str, limit: int = 0) -> list[Item]:
    """JSONL({question, gold, tags})을 Item 리스트로 로드. limit>0이면 앞에서 슬라이스."""
    items: list[Item] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(Item(**json.loads(line)))
    if limit > 0:
        items = items[:limit]
    return items


def make_wrapper(builder, model):
    """run_dataset 호출용 래퍼 — late-binding 회피 위해 기본 인자로 캡처."""

    def wrapper(emitter, run_id, builder=builder, model=model):
        return builder(model=model, emit=emitter, run_id=run_id)

    return wrapper


def print_table(rows: list[tuple[str, Report]]) -> None:
    """arch별 Report를 표로 stdout 출력."""
    cols = ["arch", "pass@1", "avg_tokens", "avg_cost", "refine", "clarify", "demote", "error"]
    widths = [10, 8, 12, 10, 8, 8, 8, 8]
    print(" ".join(f"{c:<{w}}" for c, w in zip(cols, widths, strict=True)))
    for arch, r in rows:
        vals = [
            arch,
            f"{r.pass_at_1:.3f}",
            f"{r.avg_tokens:.1f}",
            f"{r.avg_cost:.4f}",
            f"{r.refine_rate:.3f}",
            f"{r.clarify_rate:.3f}",
            f"{r.demotion_rate:.3f}",
            f"{r.error_rate:.3f}",
        ]
        print(" ".join(f"{v:<{w}}" for v, w in zip(vals, widths, strict=True)))


def main() -> None:
    parser = argparse.ArgumentParser(description="GSM8K 벤치마크 실행")
    parser.add_argument("--items", default="data/gsm8k_subset.jsonl")
    parser.add_argument("--arch", choices=["baseline", "treatment", "both"], default="both")
    parser.add_argument("--provider", default="google")
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    items = load_items(args.items, args.limit)
    model = build_model(provider=args.provider, model=args.model, temperature=args.temperature)

    builders = {}
    if args.arch in ("baseline", "both"):
        builders["baseline"] = build_baseline
    if args.arch in ("treatment", "both"):
        builders["treatment"] = build_treatment

    rows: list[tuple[str, Report]] = []
    for arch, builder in builders.items():
        report = asyncio.run(run_dataset(make_wrapper(builder, model), items))
        rows.append((arch, report))

    print_table(rows)

    # 결과 JSON 저장 — UTC 타임스탬프 파일명
    Path("data").mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path("data") / f"benchmark-{ts}.json"
    payload = {
        "args": vars(args),
        "num_items": len(items),
        "reports": {arch: report.model_dump() for arch, report in rows},
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
