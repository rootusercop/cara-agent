# CARA: Contract-Aware Refactoring Agent

**Paper:** "CARA: A Contract-Aware Refactoring Agent for Distributed Systems with Client-Exposed Data Models"

CARA is a ReAct-style LLM agent that treats schema migration and API contract evolution as a unified refactoring lifecycle. When a data model changes, CARA simultaneously analyzes both the storage layer (SQL/Protobuf schemas) and the interface layer (REST/gRPC API specs) to produce a zero-downtime expand-contract migration plan with generated adapter code.

## Quick Start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python examples/demo_field_rename.py
```

## Run Evaluation

```bash
python run_eval.py                          # all 15 cases
python run_eval.py --cases case_01 case_07  # specific cases
python run_eval.py --language kotlin        # Kotlin adapters
python run_eval.py --output results.json    # save to file
```

## Project Structure

```
cara-research/
├── agent/
│   ├── cara_agent.py       # ReAct agent + tool dispatch
│   └── prompts.py          # System prompt
├── tools/
│   ├── schema_diff.py      # SQL/Protobuf/JSON Schema diffing
│   ├── api_diff.py         # OpenAPI/Protobuf/GraphQL diffing
│   ├── consumer_tracer.py  # Cross-codebase consumer tracing
│   ├── change_classifier.py # SAFE/BACKWARD_COMPATIBLE/BREAKING
│   ├── plan_generator.py   # Expand-contract plan generation
│   ├── code_generator.py   # Adapter code generation
│   └── plan_validator.py   # Plan completeness scoring
├── eval/
│   ├── dataset/            # 15 annotated test cases
│   ├── runner.py           # Evaluation harness
│   └── metrics.py          # Precision/recall/F1 + plan metrics
├── paper/
│   ├── main.tex            # arXiv paper (LaTeX)
│   └── references.bib
└── examples/
    └── demo_field_rename.py
```

## Key Results

| Metric | CARA | Rule-only | LLM-only |
|---|---|---|---|
| Breaking Change F1 | **0.86** | 0.77 | 0.59 |
| Plan Completeness | **0.97** | N/A | 0.41 |
| Expand-Contract Compliance | **1.00** | N/A | 0.33 |
| Overall Pass Rate | **0.80** | 0.47 | 0.20 |

## Compile Paper

```bash
cd paper
pdflatex main.tex
bibtex main
pdflatex main.tex && pdflatex main.tex
```
