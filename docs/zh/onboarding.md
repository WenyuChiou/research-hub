<!-- ZH translation pending. English content below kept as a translation reference. -->

# Onboarding

`research-hub` supports a field-aware onboarding flow for new users. The goal is to get from zero configuration to a usable cluster with a fit-check prompt in one command.

## Start

```bash
research-hub init --field bio
```

You can also pre-fill every required input:

```bash
research-hub init --field edu --cluster writing-assessment --name "Writing Assessment" --query "automated writing assessment LLM feedback" --non-interactive
```

## What Happens

The onboarding wizard:

1. Chooses a field preset
2. Creates a cluster
3. Runs `discover new` with the appropriate backends
4. Writes a fit-check prompt under `.research_hub/discover/<cluster>/prompt.md`
5. Prints the next commands for `discover continue`, `ingest`, and `topic scaffold`

## Examples

Bundled starter clusters are available through:

```bash
research-hub examples list
research-hub examples show cs_swe
research-hub examples copy cs_swe --cluster my-test-cluster
```

## Doctor

After onboarding, run:

```bash
research-hub doctor
```

The doctor command validates configuration and also infers a likely field for each cluster based on note signals.
