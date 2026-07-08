# StateWeaver Agent

Local, traceable tool-calling agent MVP for NLP practice project B.

## Run

```bash
python main.py --config configs/runtime_input.json
```

Outputs are written to `outputs/<conversation_id>/`, traces to `traces/`, and checkpoints to `checkpoints/`.

## Modules

- B1 Runtime: state machine, checkpoint, trace, recovery.
- B2 Skills: calculator, file reader, file search, table analyzer, format converter, evidence checker.
- B3 Tools: schema compilation, tool routing, parameter validation, execution bridge.
- B4 Decision: planner, executor, verifier. The default MVP is local-rule based and can be replaced by Qwen/vLLM.
- B5 Memory: selective memory retrieval, write-back, versioned JSON store.
