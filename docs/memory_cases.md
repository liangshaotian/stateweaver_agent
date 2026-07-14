# Memory Test Cases

## Case 1: Repeated budget analysis

When the user repeatedly asks for budget analysis, the agent should remember that the project usually needs total cost, key cost categories and risk level. It should not duplicate the same memory item many times.

## Case 2: Preferred output language

If the user asks for Chinese output several times, the memory system may store this as a preference with a low-risk procedural note: "Prefer Chinese Markdown reports for classroom presentation."

## Case 3: Tool reliability

If the local model tool calling fails but rule-based execution succeeds, the memory system should record the fallback as a useful recovery pattern.

## Case 4: Conflicting instructions

If one file requests English output and another file requests Chinese output, the current runtime input should have higher priority than old memory records.

## Expected memory fields

Useful memory records should include type, content, source, confidence, timestamp and related task id.
