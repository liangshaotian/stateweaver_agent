# Meeting Notes

The group decided to implement five modules: runtime orchestration, skill functions, tool schema and router, local model decision, and memory management.

Discussion highlights:

- The runtime should keep messages and trace files.
- Tools should return a unified result format.
- The router should choose a small task-specific tool set.
- Memory should store user preference, successful tool paths, and failure notes.
- A demo should include document reading, table analysis, evidence checking and report generation.

Risks:

- Local model function calling may be unstable.
- GPU resources may not always be available.
- File paths and table headers may be inconsistent.
