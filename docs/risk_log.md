# Project Risk Log

## High priority risks

- Local model service may be unavailable during presentation. The fallback planner must keep the demo runnable.
- Uploaded files may contain inconsistent column names. The table analyzer should report missing fields clearly.
- Long reports may include unsupported claims. The verifier should check whether important numbers have evidence.

## Medium priority risks

- Browser users may forget to save configuration before running the agent.
- Trace files can become difficult to inspect after many repeated runs.
- Memory records may contain duplicated summaries if the same task is executed multiple times.

## Low priority risks

- Some Markdown viewers may render tables differently.
- Windows and Linux path separators may look different in logs.

## Mitigation plan

Use explicit runtime states, path validation, evidence extraction, checkpoint files and short verification summaries. During classroom demonstration, first run the default example, then switch to uploaded files for an extended scenario.
