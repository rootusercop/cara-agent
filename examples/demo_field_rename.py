"""
CARA Demo: Analyze a user_id -> account_id rename across schema and API.

Run with:
    python examples/demo_field_rename.py                    # no API key needed
    python examples/demo_field_rename.py --provider ollama  # local Ollama model
    python examples/demo_field_rename.py --provider claude  # requires ANTHROPIC_API_KEY
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agent.direct_agent import DirectCARAAgent

OLD_SCHEMA = """
CREATE TABLE accounts (
    user_id     VARCHAR(36) NOT NULL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

NEW_SCHEMA = """
CREATE TABLE accounts (
    account_id  VARCHAR(36) NOT NULL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

OLD_API = """
openapi: "3.0.0"
info:
  title: Accounts API
  version: "1.0"
paths:
  /accounts/{user_id}:
    get:
      summary: Get account
      parameters:
        - name: user_id
          in: path
          required: true
          schema: {type: string}
      responses:
        "200":
          content:
            application/json:
              schema:
                properties:
                  user_id: {type: string}
                  email: {type: string}
                  account_type: {type: string}
"""

NEW_API = """
openapi: "3.0.0"
info:
  title: Accounts API
  version: "2.0"
paths:
  /accounts/{account_id}:
    get:
      summary: Get account
      parameters:
        - name: account_id
          in: path
          required: true
          schema: {type: string}
      responses:
        "200":
          content:
            application/json:
              schema:
                properties:
                  account_id: {type: string}
                  email: {type: string}
                  account_type: {type: string}
"""


def main() -> None:
    provider = "direct"
    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider = sys.argv[idx + 1]

    if provider == "claude":
        from agent.cara_agent import CARAAgent
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("Set ANTHROPIC_API_KEY to use the Claude provider.")
            sys.exit(1)
        agent = CARAAgent(api_key=api_key)
    elif provider == "ollama":
        from agent.ollama_agent import OllamaCARAAgent
        agent = OllamaCARAAgent()
    else:
        agent = DirectCARAAgent()

    print("=" * 60)
    print("CARA Demo: user_id -> account_id rename")
    print(f"Provider: {provider}")
    print("=" * 60)

    report = agent.analyze(
        task_description=(
            "We are renaming the primary key field 'user_id' to 'account_id' "
            "across the accounts table and the Accounts API. This is a breaking "
            "change that affects all downstream consumers."
        ),
        old_schema=OLD_SCHEMA,
        new_schema=NEW_SCHEMA,
        schema_type="sql",
        old_api_spec=OLD_API,
        new_api_spec=NEW_API,
        api_spec_type="openapi",
        language="kotlin",
    )

    print("\n--- EXECUTIVE SUMMARY ---")
    print(report.executive_summary)

    print(f"\n--- CHANGE COUNTS ---")
    print(f"Schema changes: {report.schema_change_count}")
    print(f"API changes:    {report.api_change_count}")
    print(f"Breaking:       {report.breaking_count}")
    print(f"Safe:           {report.safe_count}")

    print(f"\n--- MIGRATION PLAN ({report.plan.get('step_count', 0)} steps) ---")
    for step in report.plan.get("steps", []):
        risk = step.get("estimated_risk", "")
        print(f"  Step {step['step_number']}: [{risk}] {step['title']}")
        if step.get("sql_or_code"):
            print(f"    SQL: {step['sql_or_code'][:80]}...")

    print(f"\n--- ADAPTER CODE ---")
    for code in report.adapter_codes:
        print(f"  Language: {code['language']} | Lines: {code['adapter_code_lines']} adapter + {code['test_code_lines']} test")

    print(f"\n--- VALIDATION ---")
    val = report.validation
    print(f"  Score: {val.get('completeness_score', 0):.0%} | Passed: {val.get('passed', False)}")
    for issue in val.get("issues", []):
        print(f"  [{issue['severity']}] {issue['message']}")

    print(f"\n--- REASONING TRACE ---")
    print(f"  {report.reasoning_trace_length} steps recorded")

    print("\n--- FULL REPORT (JSON) ---")
    print(json.dumps(report.to_dict(), indent=2, default=str)[:2000] + "...[truncated]")


if __name__ == "__main__":
    main()
