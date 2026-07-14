# User Feedback Notes

## Interface feedback

Users prefer a visible browser interface instead of editing raw JSON by hand. The task configuration should expose common fields such as task goal, allowed files, output formats and runtime limits.

Important comments:

- "The result panel should be in the center, because it is the main thing users read."
- "The runtime monitor should be on the right, because it is mainly used for checking progress."
- "Selecting files from the operating system file picker is easier than typing paths."
- "Chinese reports are easier to present in class than English-only reports."

## Expected agent behavior

The agent should explain what it read, what tools it used, which numbers it calculated, and which evidence lines support the final answer. If a file cannot be read, the error should be visible in the UI.

## Future improvement ideas

- Add drag-and-drop upload.
- Add one-click export for report, summary, trace and checkpoint files.
- Add a compact presentation mode for classroom screenshots.
