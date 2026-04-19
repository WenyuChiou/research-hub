---
name: Bug report
about: Something doesn't work as documented
labels: bug
---

## What happened

(One sentence)

## Steps to reproduce

```
1. ...
2. ...
3. ...
```

## What you expected

## What actually happened

(Paste relevant error message + stack trace in a code block)

## Environment

- research-hub version: `pip show research-hub-pipeline | grep Version`
- Python version: `python --version`
- OS: (Windows / macOS / Linux + version)
- Persona: (researcher / humanities / analyst / internal)
- Optional extras installed: (`[playwright]`, `[import]`, `[secrets]`, `[mcp]`, etc.)

## Doctor output

Please paste the output of:

```
research-hub doctor
```

(This catches 12+ common issues — often the answer is in here.)

## Extra context

- Vault path: `research-hub where`
- Cluster count, paper count if relevant
- Anything unusual about your setup
