# Acceptance Criteria for StateWeaver Demo

## Core requirements

The agent must read local project documents and tabular data, then produce a traceable Markdown report and a JSON summary.

Mandatory acceptance points:

1. The runtime records each major state transition, including INIT, PLAN, TOOL_CALL, VERIFY, SAVE_MEMORY and DONE.
2. The report must include evidence references from source files instead of unsupported conclusions.
3. The summary must include total budget, planned staff hours, risk level and output file paths.
4. The system must continue with a rule-based fallback when the local LLM service is not available.
5. The Web Console must allow users to configure readable files and run the agent from a browser.

## Quality checks

- The generated report should be readable in Chinese when the user requests Chinese output.
- File paths must stay within the project workspace or uploaded file directory.
- Failed tool calls should be recorded in trace files with error messages.
- Repeated runs should not silently overwrite important user-provided source files.

## Demo success definition

The demo is considered successful when the agent can read at least two documents and two tables, calculate simple totals, detect key risks, and generate both Markdown and JSON outputs.
