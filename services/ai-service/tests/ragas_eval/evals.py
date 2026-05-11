"""Run the Ragas evaluation as a script (Ragas-docs style).

Mirrors the pattern shown in the Ragas documentation: a plain Python
program that builds a dataset, calls `ragas.evaluate(...)`, prints the
score table, and writes a CSV report to `tests/ragas_eval/results/`.

It does NOT assert thresholds. For a CI regression gate, run:

    pytest -m ragas

Usage (from `services/ai-service`):

    python tests/ragas_eval/evals.py                    # all samples
    python tests/ragas_eval/evals.py --sample ecommerce_microservices
    python tests/ragas_eval/evals.py --no-save          # don't write CSV

Required envs (loaded from the repo-level `.env` automatically):

    OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SERVICE_ROOT = _THIS_FILE.parents[2]   # services/ai-service
_TESTS_ROOT = _THIS_FILE.parents[1]     # services/ai-service/tests
_REPO_ROOT = _THIS_FILE.parents[4]      # repo root (hackathon)

# When invoked as `python tests/ragas_eval/evals.py`, Python auto-prepends
# this script's directory to sys.path, which would shadow installed packages
# such as `datasets` (a transitive dependency of ragas) with our own
# `ragas_eval/datasets/` sample folder. Drop it before importing ragas.
_SCRIPT_DIR = str(_THIS_FILE.parent)
sys.path[:] = [p for p in sys.path if p != _SCRIPT_DIR]

# So `import app.*` and `import ragas_eval.*` work when launched as a script.
for path in (str(_SERVICE_ROOT), str(_TESTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env", override=False)

from openai import OpenAI  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.dataset_schema import EvaluationDataset  # noqa: E402
from ragas.llms import llm_factory  # noqa: E402

from app.adapters.outbound.strands_multi_agents_adapter import (  # noqa: E402
    SwarmLlmAdapter,
    build_multi_agents,
)
from app.config import load_settings  # noqa: E402
from ragas_eval.criteria import build_all_aspect_critics  # noqa: E402
from ragas_eval.datasets.architecture_samples import SAMPLES  # noqa: E402
from ragas_eval.helpers import build_single_turn_sample  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ragas evaluation script.")
    parser.add_argument(
        "--sample",
        action="append",
        dest="samples",
        help="Run only the named sample id (can be passed multiple times).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write a CSV report to tests/ragas_eval/results/.",
    )
    return parser.parse_args()


async def _analyze_all(adapter: SwarmLlmAdapter, samples) -> list:
    eval_samples = []
    for s in samples:
        print(f"  - analyzing sample: {s.id}")
        result = await adapter.analyze(s.ocr_text, source_hint=s.source_hint)
        eval_samples.append(
            build_single_turn_sample(
                user_input=(
                    "Analise o seguinte texto OCR de um diagrama de "
                    f"arquitetura (origem: {s.source_hint}):\n\n{s.ocr_text}"
                ),
                response=result,
                retrieved_contexts=[s.ocr_text],
            )
        )
    return eval_samples


def _select_samples(args_samples: list[str] | None):
    if not args_samples:
        return SAMPLES
    by_id = {s.id: s for s in SAMPLES}
    missing = [name for name in args_samples if name not in by_id]
    if missing:
        raise SystemExit(f"Unknown sample id(s): {missing}. Known: {list(by_id)}")
    return [by_id[name] for name in args_samples]


def main() -> int:
    args = _parse_args()

    settings = load_settings()
    if not settings.openai_api_key.get_secret_value():
        print("ERROR: OPENAI_API_KEY not set (looked at repo-level .env).")
        return 1

    samples = _select_samples(args.samples)

    print(f"[1/4] Building multi-agent swarm (model={settings.llm_model})...")
    adapter = SwarmLlmAdapter(swarm=build_multi_agents())

    print(f"[2/4] Running analysis on {len(samples)} sample(s)...")
    eval_samples = asyncio.run(_analyze_all(adapter, samples))

    print("[3/4] Building Ragas judge and metrics...")
    judge_client = OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
    )
    judge = llm_factory(
        settings.llm_model,
        client=judge_client,
        temperature=0.0,
    )
    metrics = build_all_aspect_critics(judge)

    print("[4/4] Evaluating with Ragas...")
    dataset = EvaluationDataset(samples=eval_samples)
    result = evaluate(dataset=dataset, metrics=metrics, show_progress=True)

    df = result.to_pandas()

    print("\n=== Per-sample scores ===")
    print(df.to_string(index=False))

    print("\n=== Mean scores ===")
    for metric in metrics:
        mean = float(df[metric.name].fillna(0.0).mean())
        print(f"  {metric.name:35s} {mean:.3f}")

    if not args.no_save:
        out_dir = _THIS_FILE.parent / "results"
        out_dir.mkdir(exist_ok=True)
        out_csv = out_dir / f"eval_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(out_csv, index=False)
        print(f"\nReport saved to {out_csv.relative_to(_SERVICE_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
