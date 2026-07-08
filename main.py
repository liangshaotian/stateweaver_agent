from __future__ import annotations

import argparse
from pathlib import Path

from b1_runtime.runtime import AgentRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="StateWeaver Agent")
    parser.add_argument("--config", default="configs/runtime_input.json")
    args = parser.parse_args()
    runtime = AgentRuntime(Path(args.config))
    result = runtime.run()
    print("StateWeaver run finished")
    print(f"conversation_id={result['conversation_id']}")
    print(f"status={result['status']}")
    print(f"report={result.get('report_path')}")
    print(f"summary={result.get('summary_path')}")
    print(f"trace={result.get('trace_path')}")


if __name__ == "__main__":
    main()
