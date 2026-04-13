<!-- ZH translation pending. English content below kept as a translation reference. -->

# Quickstart

## Install

```bash
pip install research-hub-pipeline[mcp]
```

## Initialize

Run the setup wizard:

```bash
research-hub init --vault ~/knowledge-base
```

Or start with the field-aware onboarding flow:

```bash
research-hub init --field cs
```

## Verify

```bash
research-hub doctor
```

## Search

```bash
research-hub search "LLM agent software engineering benchmark" --field cs
```

## Discover

```bash
research-hub discover new --cluster llm-agents --query "LLM agent software engineering benchmark" --field cs
```

Then score the generated fit-check prompt and continue:

```bash
research-hub discover continue --cluster llm-agents --scored scored.json --auto-threshold
```

## Ingest

```bash
research-hub ingest --cluster llm-agents --fit-check
```

## Continue

- Build topic notes with `research-hub topic scaffold --cluster <slug>`
- Browse bundled examples with `research-hub examples list`
- Launch the local dashboard with `research-hub dashboard`
