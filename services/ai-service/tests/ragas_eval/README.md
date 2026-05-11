# Ragas evaluation suite

This folder holds a [Ragas](https://docs.ragas.io)-powered behavioral
evaluation for the multi-agent architecture-analysis flow
(`SwarmLlmAdapter`).

It is intentionally **not** part of the pytest suite. It runs as a standalone
script and is meant for ad-hoc / manual evaluation, matching the pattern in
the Ragas documentation:

```bash
python evals.py
```

## Layout

```
tests/ragas_eval/                 # named *_eval to avoid shadowing the `ragas` package
├── criteria.py                   # shared AspectCritic definitions
├── datasets/
│   └── architecture_samples.py   # curated golden OCR samples
├── helpers.py                    # AnalysisResult -> evaluation text
├── evals.py                      # runnable script
└── results/                      # generated CSV reports (gitignored)
```

## Setup

The eval dependencies are kept **separate** from the unit-test dependencies
so a regular `pip install -r requirements-dev.txt` stays lean.

```bash
cd services/ai-service
pip install -r requirements-eval.txt
```

## How to run

The script auto-loads the repo-level `.env`, so the OpenRouter envs come
straight from there (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `LLM_MODEL`).

```bash
# from services/ai-service
python tests/ragas_eval/evals.py

# only one sample
python tests/ragas_eval/evals.py --sample ecommerce_microservices

# do not write a CSV report
python tests/ragas_eval/evals.py --no-save
```

Output:

- a per-sample score table printed to stdout,
- a mean score per metric,
- a CSV report under `tests/ragas_eval/results/eval_<timestamp>.csv` (unless `--no-save`).

## Configuration

| env var          | default                          | purpose                            |
| ---------------- | -------------------------------- | ---------------------------------- |
| `OPENAI_API_KEY` | _(required)_                     | OpenRouter API key                 |
| `OPENAI_BASE_URL`| `https://openrouter.ai/api/v1`   | OpenRouter-compatible base URL     |
| `LLM_MODEL`      | `deepseek/deepseek-v3.2`         | Model used by the swarm and judge  |
| `LLM_OCR`        | `google/gemma-4-26b-a4b-it:free` | OCR model for the OCR adapter      |

All other swarm parameters (`MAX_HANDOFFS`, `EXECUTION_TIMEOUT`, etc.) are
read from the same `.env` via `app.config.load_settings()`.

## What is being evaluated

Every metric is a Ragas `AspectCritic` (natural-language criterion → 0/1
verdict) defined in `criteria.py`:

| critic name                  | criterion                                             |
| ---------------------------- | ----------------------------------------------------- |
| `brazilian_portuguese`       | Output is in Brazilian Portuguese                     |
| `grounded_in_input`          | No components hallucinated outside the OCR text       |
| `risks_and_mitigations`      | ≥3 risks, each with a mitigation/recommendation       |
| `components_match_topology`  | Component list reflects the topology in the OCR text  |

## Adding new samples

1. Append an `ArchitectureSample` to `datasets/architecture_samples.py`.
2. Re-run the script — the new sample is picked up automatically.

## Adding new criteria

Add a new `CriticSpec` to `criteria.py`. The script picks it up automatically
via `build_all_aspect_critics`. Keep definitions binary and unambiguous;
that is what makes `AspectCritic` reliable.
