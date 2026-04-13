# Changelog

## v0.20.2 (2026-04-13)

**Backend live-behavior fixes + honest coverage audit.** A session-ending audit ran each of the 13 registered backends against a real query designed to hit its strongest coverage area. **Only 4 of 13 returned correct results end-to-end.** Mocked unit tests were passing but the live APIs behaved differently from the test fixtures. v0.20.2 fixes the three most impactful issues and documents the rest as known-broken for v0.21.

### Fixed

- **arXiv backend (`search/arxiv_backend.py`)** — the search query was wrapped in quotes as `all:"LLM agent software engineering"`, which arXiv interprets as a phrase match requiring the exact sequence. No paper's metadata contains that exact string, so live queries returned 0 results for the entire v0.13.0-v0.20.1 period. Live audit confirmed 0 hits against "LLM agent software engineering" while a raw API call with AND-joined terms returned 5 relevant papers.
  - **Fix:** new `_build_arxiv_query()` helper that splits free-text queries into `all:term1 AND all:term2 AND ...`, preserves explicit quoted phrases, and falls back to `all:*` on empty input.
  - **Verified live:** post-fix returns 5 on-topic papers (SkillMOO, SWE-bench bug triggers, Tokalator, From LLMs to LLM-based Agents, etc.).
  - **Regression tests:** 4 new tests in `test_arxiv_backend.py` covering AND-split, quoted-phrase preservation, empty fallback, single-word.

- **bioRxiv backend (`search/biorxiv.py`)** — `_matches_query()` used `any(...)`, so a 4-word query matched any paper containing at least one query word. Live audit returned papers about "heavy metal bacterial adaptation" for a query about "protein structure prediction AlphaFold" because both use the word "protein".
  - **Fix:** switched to strict AND — all query terms must be present in the title or abstract.
  - **Trade-off:** strict AND returns 0 results for specific multi-word queries where bioRxiv doesn't have a matching paper, instead of returning irrelevant papers. The honest-zero behavior is better for downstream fit-check and ranking.
  - **Regression tests:** updated `test_biorxiv_matches_query_requires_all_terms` to assert strict AND semantics with 4/4, 3/4, 2/4, 1/4 term cases.

- **Semantic Scholar backend (`search/semantic_scholar.py`)** — on HTTP 429 the backend silently returned an empty list with no user-facing signal, making it impossible to distinguish "no results" from "rate-limited". Live audit hit 429 on every run because S2's free tier throttles aggressively.
  - **Fix:** added a `logger.warning()` with a link to the API key signup page. Existing silent return behavior preserved for callers that don't want to fail on rate limit; visible warning tells the user why they're getting zero results.

### Known issues deferred to v0.21

These were surfaced by the live audit but need a larger fix than a patch release:

- **DBLP** — query uses substring matching that accepts "Swedish" as a match for "SWE-bench". Needs a word-boundary regex or a different API query strategy.
- **ChemRxiv** — ChemRxiv migrated off the Figshare API around 2022-2023; group_id 13652 returns empty results. Needs the Cambridge Open Engage API.
- **RePEc** — the IDEAS HTML scraper's regex pattern (`/p/<series>/<handle>.html`) matches zero handles against the current HTML. Needs a rewrite against either the current DOM or the OAI-PMH endpoint directly (skipping the HTML handle-list step).
- **CiNii** — live audit confirmed the backend parses the Atom XML correctly, but the `from`/`until` year filter excludes all results because CiNii dates everything as the current year (2026) by default. Needs verification of CiNii's date field semantics.
- **KCI** — the endpoint URL returned HTML not JSON in the live audit. The KCI public REST API may live at a different path or may not exist at all. Needs investigation.
- **NASA ADS** — correctly reports `ADS_DEV_KEY` missing at runtime. Not a bug, just requires the user to set the env var.

### Working backends after v0.20.2 (5 of 13)

| Backend | Live status | Use case |
|---|---|---|
| OpenAlex | ✅ | general STEM + humanities |
| arXiv | ✅ (post-fix) | CS, math, physics, bio preprints |
| Crossref | ✅ | DOI-authoritative metadata, all fields |
| PubMed | ✅ | biomedicine |
| ERIC | ✅ | education research |

Plus **Semantic Scholar** when not rate-limited (intermittent).

### Tests

- **735 → 740 passing** (+5 regression tests, 5 skipped unchanged).
- `test_arxiv_backend.py`: 4 tests for `_build_arxiv_query()`.
- `test_biorxiv_backend.py`: 1 test for strict AND filter.

## v0.20.1 (2026-04-13)

**Bug fix.** v0.14.0-B's `_update_subtopic_frontmatter` (called when `topic build` runs on an existing sub-topic file) dropped the trailing newline before the closing `---` fence, producing corrupted frontmatter like:

```yaml
papers: 10
status: draft---     ← missing newline before the fence
```

The corrupted YAML broke `_extract_frontmatter_block`'s `text.find("\n---\n", 4)` lookup, which made `_existing_subtopic_paper_count` return 0 for every sub-topic file, which made `research-hub topic list` show every cluster as having 0 papers per sub-topic — even though the sub-topic notes themselves contained the correct paper lists.

Bug surfaced during a real live test on the cleaned-up `llm-agents-software-engineering` cluster (8 papers expanded to 20 via `discover new` + `discover continue --auto-threshold`, then sub-topic notes built). The first `topic build` worked; the second `topic build` (after re-running `topic assign apply` with corrected paper slugs) corrupted the frontmatter.

**Fix:** one-character change to add the missing `\n` between the frontmatter body and the closing fence in `_update_subtopic_frontmatter`'s return value.

**Regression test added:** `test_build_subtopic_notes_rerun_preserves_frontmatter_yaml` runs build twice and asserts the YAML closing fence stays on its own line, plus verifies `list_subtopics()` returns the correct paper count after rebuild.

Tests: 734 → 735 passing (+1 regression test).

## v0.20.0 (2026-04-13)

**CJK literature backends + region preset — Japanese and Korean academic literature now first-class.**

After v0.19, research-hub covered all major Western fields (CS, biomedicine, social science, chemistry, astronomy, education) but every backend assumed English-language content. Anyone searching for Japanese, Korean, or Chinese literature got nothing — a hard miss for ~15% of the world's research output and a major gap for researchers in Asia. v0.20 adds two CJK-region academic search backends and a `--region` preset that mirrors the `--field` pattern but selects backends by language/region instead of discipline.

### Added — Two CJK backends

- **`CiniiBackend`** (`src/research_hub/search/cinii.py`, ~150 LOC) — CiNii Research, run by Japan's National Institute of Informatics (NII). The canonical bibliography for Japanese academic literature: ~26M records covering Japanese journals, conference proceedings, theses, books, projects. Free, no API key required. Uses the OpenSearch Atom XML endpoint at `https://cir.nii.ac.jp/opensearch/all` with year filters via `from`/`until` params. Parses Atom + Dublin Core + PRISM + CiNii namespaces, extracts DOI from multiple identifier formats (`https://doi.org/...`, `info:doi/...`, `prism:doi`). doc_type maps from `dc:type` to `journal-article`/`thesis`/`book`/`conference-paper`. Japanese characters in titles preserved verbatim.

- **`KciBackend`** (`src/research_hub/search/kci.py`, ~150 LOC) — Korea Citation Index, run by the Korean National Research Foundation. Covers Korean academic literature across all disciplines. Free OpenAPI access at `https://www.kci.go.kr/kciportal/po/search/poArtiSearList.kci` for basic queries, no key required. JSON API. Tries multiple field name variants (`titleEng` first, falling back to `title`; `authors`/`authorList`; `journalNameEng`/`journalName`) to be robust against schema drift. Year filter via `startYear`/`endYear` params.

### Added — `--region` preset

New flag on `research-hub search` and `research-hub discover new`, **mutually exclusive with `--backend` and `--field`**:

| Region preset | Backends |
|---|---|
| `en` | v0.16 5-backend list (DEFAULT_BACKENDS) |
| `jp` | openalex + cinii + crossref |
| `kr` | openalex + kci + crossref |
| `cjk` | openalex + cinii + kci + crossref |

Resolution priority: `--region` > `--field` > `--backend` > `DEFAULT_BACKENDS`. The CLI `add_mutually_exclusive_group` enforces that only one of the three flags can be supplied at a time.

### Backend registry

`_BACKEND_REGISTRY` now has **14 entries (13 unique classes + `medrxiv` alias)**:

```python
_BACKEND_REGISTRY = {
    # ... v0.16-v0.19 entries ...
    "cinii": CiniiBackend,    # NEW
    "kci": KciBackend,        # NEW
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — CJK backends are opt-in.

### CLI / MCP

- `--region` flag on `search` and `discover new` (mutually exclusive with `--backend` and `--field`)
- `discover_new` Python function gains `region: str | None = None` parameter
- `search_papers` and `discover_new` MCP tools gain `region: str | None = None` parameter
- **No new MCP tools** — 45 stays.

### Bilingual docs

- **`docs/zh/cli-reference.md`** (297 lines) — Traditional Chinese translation of `docs/cli-reference.md` (302 lines). Completes the v0.19.0 ZH translation pass that hit a Gemini rate limit on the third file. All four `docs/zh/*.md` files now have full translations.

### Tests

- **702 → 734 passing** (+32 tests, 5 skipped unchanged).
- `tests/test_cinii_backend.py`: 12 tests (Atom XML parsing, multi-namespace identifier extraction, Japanese characters, year filter, doc_type mapping).
- `tests/test_kci_backend.py`: 12 tests (titleEng fallback, authors as list/dict/string, year filter, articleId URL building).
- `tests/test_region_preset.py`: 2 tests for jp/cjk presets.
- Existing fallback / CLI / discover / MCP tests updated.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, default backend list, and import paths continue to work unchanged. `--region` is purely additive but mutually exclusive with the existing `--backend` and `--field` flags.

### Field + region coverage matrix

After v0.20 (combining v0.16-v0.20):

| Coverage axis | Options |
|---|---|
| **Field presets (11)** | cs, bio, med, physics, math, social, econ, chem, astro, edu, general |
| **Region presets (4)** | en, jp, kr, cjk |
| **Total backends (13)** | OpenAlex, arXiv, Semantic Scholar, Crossref, DBLP, PubMed, bioRxiv, RePEc, ChemRxiv, NASA ADS, ERIC, CiNii, KCI |

### Deferred to v0.21+

- **Chinese-language backends** — CSSCI/CNKI require institutional subscriptions; deferred until a free open path exists
- **Cross-CJK title fuzz match** — current title-similarity dedup uses Latin word boundaries, doesn't handle CJK boundaries well; v0.21 candidate
- **JSTOR / PsycINFO / IEEE Xplore** — paid databases, lower priority

## v0.19.1 (2026-04-13)

**Build fix.** v0.19.0 wheel was rejected by PyPI with a 400 Bad Request because the wheel had **duplicate file entries** for `research_hub/examples/*`. The `[tool.hatch.build.targets.wheel] packages = ["src/research_hub"]` already includes the `examples/` subpackage automatically, but the additional `[tool.hatch.build.targets.wheel.force-include]` section added the same files a second time. Removing the redundant `force-include` block fixes the duplicate entries; `twine check` now PASSES and the wheel uploads cleanly. No code changes — same v0.19.0 features, just a working build.

## v0.19.0 (2026-04-13)

**Onboarding wizard + bundled examples + bilingual docs scaffolding — lower the barrier for non-CS users.**

After v0.18.0, research-hub had 11 backends and 11 field presets but a brand-new researcher still had to read three docs and stitch six CLI calls together to create their first cluster. v0.19 ships an interactive `init --field <slug>` wizard that walks through cluster creation + first `discover` run with field-appropriate defaults, plus a bundled examples library so users can copy a working cluster definition instead of inventing one from scratch.

### Added — `research-hub init --field <slug>` wizard

- **`src/research_hub/onboarding.py`** (~250 LOC) — field-aware wizard that:
  1. Prompts for cluster name + slug (auto-derived from name)
  2. Prompts for query + optional definition
  3. Creates the cluster registry entry
  4. Runs `discover_new()` internally with the field preset (so the user gets a fit-check prompt without having to call `discover new` themselves)
  5. Prints next-steps with copy-pasteable commands
- **Both interactive and scriptable.** `--non-interactive` mode requires all flags (`--field`, `--cluster`, `--name`, `--query`) and runs end-to-end without input prompts.
- **Existing `init` (no `--field`) unchanged** — calls the legacy `init_wizard.run_init()` for backwards compatibility.

### Added — Field-aware `doctor` check

- **`src/research_hub/doctor_field.py`** (~120 LOC) — for each cluster, scans paper notes for venue/keyword signals and infers the dominant field. Compares against the cluster's declared field (inferred from `seed_keywords`) and reports a `WARN` when they disagree.
- Surfaces in `research-hub doctor` output as `cluster_field:<slug>`. Example: `WARN cluster_field:my-cluster: declared field=cs but papers look like bio (confidence=0.78, signal=12)`.
- Signal keywords cover all 11 fields (cs, bio, med, physics, math, astro, chem, social, econ, edu, general).

### Added — `research-hub examples {list, show, copy}` subcommand group

- **`src/research_hub/examples/`** — bundled example cluster definitions:
  - `cs_swe.json` — LLM agents for software engineering
  - `bio_protein.json` — protein structure prediction
  - `social_climate.json` — climate adaptation modeling
  - `edu_assessment.json` — automated writing assessment with LLMs
- Each example has `name`, `slug`, `field`, `query`, `definition`, `year_from`/`year_to`, `min_citations`, `sample_dois`, `description`.
- `research-hub examples list` — print all 4 with field tags
- `research-hub examples show <name>` — full JSON definition
- `research-hub examples copy <name> [--cluster <slug>]` — copy as a new cluster in the user's `clusters.yaml`, ready for `discover new`
- **3 new MCP tools** (45 total): `examples_list`, `examples_show`, `examples_copy`
- Wheel build now `force-include`s the `examples/` directory via `[tool.hatch.build.targets.wheel.force-include]`.

### Added — Bilingual docs scaffolding

- **`docs/onboarding.md`** (English, new) — first-time setup, three personas (CS researcher, biomedicine PhD, social science postdoc), wizard walkthrough, field reference table.
- **`docs/zh/`** — directory scaffolded with English placeholder content + `<!-- ZH translation pending -->` markers in each file:
  - `docs/zh/README.md` — Chinese entry point with translation status
  - `docs/zh/quickstart.md` — quickstart stub
  - `docs/zh/onboarding.md` — onboarding stub
  - `docs/zh/ai-integrations.md` — integration guide stub
- **A separate Gemini pass** will translate these stubs to traditional Chinese in v0.19.x. Codex did not write Chinese content because CJK content is poorly handled by Codex per the project delegation rules.

### Tests

- **680 → 702 passing** (+22 tests, 5 skipped unchanged).
- `tests/test_onboarding.py`: 10 tests for wizard interactive/non-interactive flows + examples loader.
- `tests/test_doctor_field.py`: 6 tests for field inference signals + doctor warnings.
- `tests/test_examples_cli.py`: 4 tests for CLI surface (list/show/copy/init --field).
- `tests/test_cli_init_doctor.py`, `tests/test_consistency.py`: extended for new commands and MCP tools.

### Non-breaking changes only

- Existing `init`, `doctor`, `examples`-namespace-free CLI all unchanged.
- `--field` flag on `init` is purely additive.
- All v0.18.0 features and import paths preserved.

### Deferred to v0.19.x and v0.20+

- **Chinese translation pass** for `docs/zh/` — separate Gemini run, lighter than this release.
- **CJK literature backends** (CiNii Japan, KCI Korea) — non-trivial encoding + API access challenges; v0.20 candidate.
- **Field auto-detection at cluster creation** — currently doctor warns after the fact; in v0.20+ the wizard could pre-validate the user's chosen field against their seed keywords.

## v0.18.0 (2026-04-13)

**Three more domain backends — chemistry, astronomy/astrophysics, education now first-class.**

v0.17.0 covered CS, biomedicine, social science, economics. v0.18.0 fills in the remaining major fields a research university actually has: chemistry (ChemRxiv), astronomy/astrophysics/geophysics (NASA ADS), and education (ERIC). After this release, the workflow generalizes from "STEM + biomedicine + social science" to "STEM + biomedicine + social science + chemistry + astronomy + education" — most disciplines covered.

### Added — Three more backends

- **`ChemrxivBackend`** (`src/research_hub/search/chemrxiv.py`, ~110 LOC) — ChemRxiv runs on Figshare's infrastructure. Uses the public Figshare API at `https://api.figshare.com/v2/articles/search` with `group_id=13652` to filter to ChemRxiv-hosted content. Free, no key. Returns title, authors, year, DOI, abstract, doc_type=`preprint`. The de-facto chemistry preprint server, same role as bioRxiv for biology.

- **`NasaAdsBackend`** (`src/research_hub/search/nasa_ads.py`, ~150 LOC) — NASA Astrophysics Data System REST API at `https://api.adsabs.harvard.edu/v1/search/query`. Reads API key from `ADS_DEV_KEY` environment variable; without a key the backend returns `[]` and logs a one-time WARNING (graceful degradation, never crashes). Get a free key at https://ui.adsabs.harvard.edu/user/settings/token. Covers ~16M records: astronomy, astrophysics, solar physics, planetary science, geophysics, Earth science. ADS query syntax (`year:[2024 TO 2025]`, `doi:"..."`, `bibcode:"..."`) is used for filters and lookups.

- **`EricBackend`** (`src/research_hub/search/eric.py`, ~120 LOC) — ERIC (Education Resources Information Center), run by the U.S. Institute of Education Sciences. Public REST API at `https://api.ies.ed.gov/eric/`. Free, no key. ~2M records covering education research papers, theses, and ED reports. Maps ERIC IDs to doc types (`EJ`-prefixed = `journal-article`, `ED`-prefixed = `report`).

### Added — Three new field presets

| Preset | Backends |
|---|---|
| `chem` | openalex + chemrxiv + crossref + semantic-scholar |
| `astro` | openalex + arxiv + nasa-ads + crossref + semantic-scholar |
| `edu` | openalex + eric + crossref + semantic-scholar |

The `general` preset now expands to **11 backends** (was 8 in v0.17): the v0.16 + v0.17 + v0.18 set combined.

### Backend registry

`_BACKEND_REGISTRY` now has **12 entries (11 unique classes + `medrxiv` alias for `BiorxivBackend`)**:

```python
_BACKEND_REGISTRY = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,    # alias
    "repec": RepecBackend,
    "chemrxiv": ChemrxivBackend,    # NEW
    "nasa-ads": NasaAdsBackend,     # NEW
    "eric": EricBackend,            # NEW
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — the new domain backends are still opt-in.

### CLI / MCP — no signature changes

The `--field` flag's `choices=sorted(FIELD_PRESETS.keys())` is computed dynamically, so adding new presets to `FIELD_PRESETS` automatically extends the CLI. The `discover_new` and `search_papers` MCP tools accept the new preset names without any signature changes. **No CLI parser modifications, no MCP tool count change (42 stays).**

### Tests

- **652 → 680 passing** (+28 tests, 5 skipped unchanged).
- `tests/test_chemrxiv_backend.py`: 8 tests (POST + JSON body, `group_id=13652` assertion, year filter, doc_type=preprint).
- `tests/test_nasa_ads_backend.py`: 8 tests (graceful degradation without API key, Bearer auth header, year range query, DOI/bibcode lookup).
- `tests/test_eric_backend.py`: 8 tests (year filter via `publicationdateyear`, EJ vs ED doc_type mapping, authors as string or list).
- `tests/test_field_preset.py`: 3 new tests for chem/astro/edu presets.
- `tests/test_search_fallback.py`: registry assertion test for the 3 new backends.

### Field coverage matrix after v0.18.0

| Domain | Backends | Preset |
|---|---|---|
| CS / SE / AI | openalex + arxiv + s2 + dblp + crossref | `--field cs` |
| Math / theoretical physics | openalex + arxiv + crossref + s2 | `--field math` |
| Applied physics / astronomy | openalex + arxiv + nasa-ads + crossref + s2 | `--field astro` |
| Biology | openalex + pubmed + biorxiv + crossref + s2 | `--field bio` |
| Medicine | openalex + pubmed + biorxiv + crossref + s2 | `--field med` |
| Chemistry | openalex + chemrxiv + crossref + s2 | `--field chem` |
| Civil / environmental engineering | openalex + crossref + s2 (general STEM) | `--field general` (no specialty backend) |
| Economics / social science | openalex + crossref + s2 + repec | `--field social` / `--field econ` |
| Education | openalex + eric + crossref + s2 | `--field edu` |
| Humanities | openalex + crossref + s2 (general) | `--field general` (no specialty backend) |

### Deferred to v0.19+

- **CJK literature backends** (CiNii Japan, KCI Korea) — non-trivial encoding + API access challenges
- **JSTOR / PsycINFO** for humanities + psychology — paid databases, lower priority
- **IEEE Xplore** for EE/CE — paid API
- **Bilingual docs + onboarding wizard** — `research-hub init --field bio` walkthrough, EN/ZH per-field quickstarts

## v0.17.0 (2026-04-13)

**Domain backends + field preset — biology, medicine, economics, social sciences now first-class.**

v0.16.0 covered CS / general STEM well but left biomedicine, economics, and social sciences under-served. This release adds three high-impact domain backends and a `--field` preset shortcut so a researcher in biomedicine doesn't need to know which backends fit their field — they say `--field bio` and get the right combination automatically.

### Added — Three new domain backends

- **`PubMedBackend`** (`src/research_hub/search/pubmed.py`, ~150 LOC) — NCBI E-utilities API, free, no key required (key gives 10 req/s instead of 3 req/s, not needed for typical search loads). Two-step request flow: `esearch.fcgi` returns PMID list, `esummary.fcgi` returns structured metadata. Returns title, authors, year, journal, DOI, doc_type. PubMed does not return abstracts via esummary — relies on the merge layer to fill abstracts from other backends. Year filter uses `[pdat]` term tag, DOI lookup uses `[doi]` tag. ~35M biomedical citation database, the canonical biomedicine source.

- **`BiorxivBackend`** (`src/research_hub/search/biorxiv.py`, ~120 LOC) — bioRxiv + medRxiv preprint aggregator. Single backend that queries both servers (biology + medical preprints) and merges results. The official biorxiv API has no free-text search endpoint, so the backend fetches a date window (`/details/{server}/{date_from}/{date_to}/{cursor}`) and filters client-side by query terms. Inefficient but the only option without HTML scraping. Registered as both `biorxiv` and `medrxiv` (alias) in the backend registry.

- **`RepecBackend`** (`src/research_hub/search/repec.py`, ~180 LOC) — RePEc (Research Papers in Economics) via OAI-PMH XML protocol. Two-stage like PubMed: scrape IDEAS HTML search results to get RePEc handle list (`/p/<series>/<handle>.html` regex), then fetch metadata for each handle via OAI-PMH `GetRecord` request. Parses Dublin Core XML (`dc:title`, `dc:creator`, `dc:date`, `dc:identifier`, `dc:type`). The IDEAS HTML scraping is fragile (could break if RePEc changes their markup), but it's the only viable free option. ~3M economics records, cross-publisher coverage.

### Added — `--field` preset shortcut

New flag on `research-hub search` and `research-hub discover new`:

```bash
research-hub search "..." --field bio
research-hub discover new --cluster X --field social --query "..."
```

Available presets:

| Preset | Backends |
|---|---|
| `cs` | openalex + arxiv + semantic-scholar + dblp + crossref |
| `bio` | openalex + pubmed + biorxiv + crossref + semantic-scholar |
| `med` | openalex + pubmed + biorxiv + crossref + semantic-scholar |
| `physics` | openalex + arxiv + crossref + semantic-scholar |
| `math` | openalex + arxiv + crossref + semantic-scholar |
| `social` | openalex + crossref + semantic-scholar + repec |
| `econ` | openalex + crossref + semantic-scholar + repec |
| `general` | all 8 backends |

`--field` and `--backend` are **mutually exclusive** (CLI rejects both at once with a clear error). Default if neither supplied: keep v0.16.0 default (5 backends — `openalex,arxiv,semantic-scholar,crossref,dblp`).

### Backend registry

`_BACKEND_REGISTRY` now includes the 3 new backends + `medrxiv` alias for `BiorxivBackend`:

```python
_BACKEND_REGISTRY = {
    "openalex": OpenAlexBackend,
    "arxiv": ArxivBackend,
    "semantic-scholar": SemanticScholarClient,
    "crossref": CrossrefBackend,
    "dblp": DblpBackend,
    "pubmed": PubMedBackend,
    "biorxiv": BiorxivBackend,
    "medrxiv": BiorxivBackend,    # alias — same backend queries both servers
    "repec": RepecBackend,
}
```

`DEFAULT_BACKENDS` stays at the v0.16.0 5-backend list — the new domain backends are opt-in via `--field` or explicit `--backend`.

### MCP surface

- `search_papers` and `discover_new` MCP tool signatures gain optional `field: str | None = None` parameter. When set, it overrides `backends`. Backwards compatible: omitting it restores v0.16.0 behavior.
- **No new MCP tools** — 42 tools total.

### Tests

- **618 → 652 passing** (+34 tests, 5 skipped unchanged).
- `tests/test_pubmed_backend.py`: 8 tests for the two-step esearch+esummary flow.
- `tests/test_biorxiv_backend.py`: 6 tests covering both servers, date window, query filter.
- `tests/test_repec_backend.py`: 8 tests for HTML scraping + OAI-PMH XML parsing.
- `tests/test_field_preset.py`: 8 tests for preset resolution + mutex with `--backend`.
- Existing fallback / CLI / discover tests updated.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, default backend list, and import paths continue to work unchanged. `--field` is purely additive.

### Deferred to v0.18+

- **NASA ADS** for astronomy/physics
- **ChemRxiv** for chemistry preprints
- **ERIC** for education research
- **IEEE Xplore** (paid API, lower priority)
- **JSTOR** for humanities (paid)

## v0.16.0 (2026-04-13)

**Multi-backend that actually works + filters + smart ranking — fixes the gaps live tests #2 and #3 surfaced.**

v0.13.0 promised a three-backend fallback chain but live tests revealed it was functionally single-backend: 29/29 candidates across both test runs came from OpenAlex; arXiv and Semantic Scholar contributed zero hits. Root cause: arXiv preprints have zero citations by definition, so the global `min_citations` filter dropped all of them. Test #3 also showed citation-count sort actively hurting noisy queries — IPCC/Lancet reports with 2000+ citations dominated the top 5 positions while the actually-relevant migration papers (with <50 cits) ranked lower. This release fixes the multi-backend chain, adds two new specialized backends, and replaces the citation sort with a smart ranking heuristic.

### Added — Two new backends

- **`CrossrefBackend`** (`src/research_hub/search/crossref.py`, ~140 LOC) — Crossref REST API, free, no key required. Cross-publisher DOI metadata via `https://api.crossref.org/works`. Filters by `type:journal-article` to bias toward primary research. Returns title, authors, year, journal, doc_type, citation count. Does NOT return abstracts (Crossref doesn't store them) — used as a confidence-booster + type-filter source, not a primary search.
- **`DblpBackend`** (`src/research_hub/search/dblp.py`, ~140 LOC) — DBLP computer science bibliography, free, no key. 100% coverage of CS/SE publications including workshop papers and preprints OpenAlex misses. JSON API at `https://dblp.org/search/publ/api`. Returns title, authors, year, venue, doc_type. No abstracts, no citation counts (DBLP doesn't expose them) — used as a recall-boost for SE/CS topics.

### Added — Confidence merging + smart ranking

- **`SearchResult` gains three fields:**
  - `confidence: float` (0.5–1.0) — `0.5 + 0.25 * (n_backends_found - 1)` clamped to 1.0
  - `found_in: list[str]` — which backends saw this paper
  - `doc_type: str` — OpenAlex-style document type (journal-article, book-chapter, report, preprint, etc)
- **`search/_rank.py`** (new module, ~80 LOC) — `merge_results()`, `confidence_from_backends()`, `rank()`, `apply_filters()`, `_term_overlap()`.
- **Smart ranking** (default): `2 * confidence + recency + relevance` where recency is `max(0, 1 - 0.2 * (current_year - paper_year))` and relevance is the fraction of query terms present in the paper's title+abstract. Replaces the legacy citation-count-descending sort, which biased toward popular-but-irrelevant survey papers on polysemous queries.
- **Legacy ranking preserved:** `--rank-by citation` restores v0.15.0 behavior; `--rank-by year` sorts by recency only; default `--rank-by smart` is the new heuristic.

### Added — Filter flags on `research-hub search` and `research-hub discover new`

- **`--exclude-type "book-chapter,report,paratext"`** — drops results whose `doc_type` matches any of the listed types. Useful for filtering out IPCC synthesis docs, Lancet review reports, etc.
- **`--exclude "ipcc lancet burden plastic"`** — negative keywords. Drops results whose title or abstract contains any listed term (case-insensitive substring match).
- **`--min-confidence 0.75`** — requires the paper to be found by at least 2 backends (confidence 0.5 = single backend, 0.75 = two, 1.0 = three or more).
- **`--backend-trace`** — logs per-backend hit counts before merge so you can see exactly why a backend returned nothing.
- **`--rank-by {smart,citation,year}`** — pick ranking strategy.

### Fixed — multi-backend now actually multi-backend

- **`search/fallback.py::search_papers` reworked** to call each backend with appropriate filters:
  - **arXiv** ignores `min_citations` (preprints have zero citations by definition — root cause of v0.13.0 gap #6)
  - **Other backends** apply `min_citations` as before
  - All backends still respect the `year_from`/`year_to` filter
- Per-backend over-fetch (`per_backend_limit = max(limit*2, 20)`) so the merge step still has enough candidates after dedup.
- Backend trace mode logs hit counts at WARNING level when enabled.

### Default backend list

`DEFAULT_BACKENDS` is now `("openalex", "arxiv", "semantic-scholar", "crossref", "dblp")` — 5 backends instead of 3. Existing `--backend openalex,arxiv,semantic-scholar` still works (explicit list overrides the default).

### MCP surface

- `search_papers` and `discover_new` MCP tool signatures gain optional `exclude_types`, `exclude_terms`, `min_confidence`, `rank_by` parameters. Backwards compatible: omitting them restores v0.15.0 behavior.
- **No new MCP tools** — 42 tools total.

### Tests

- **581 → 618 passing** (+37 tests, 5 skipped unchanged).
- `tests/test_crossref_backend.py`: 6 tests for the Crossref backend (mocked HTTP).
- `tests/test_dblp_backend.py`: 6 tests for the DBLP backend (mocked HTTP, fixture JSON).
- `tests/test_search_confidence.py`: 8 tests for confidence merging across backends.
- `tests/test_search_filters.py`: 10 tests for filter flags and ranking modes.
- Existing fallback / CLI / MCP / discover tests updated for new fields and signatures.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and import paths continue to work unchanged. The new ranking is the new default but legacy citation sort is one flag away.

### Deferred to v0.17+

- **PubMed / bioRxiv / medRxiv backends** for biology/medicine — v0.17
- **RePEc backend** for economics/social science — v0.17
- **`--field bio|med|cs|social|...` preset** for newcomers — v0.17
- **NASA ADS / ChemRxiv / ERIC backends** — v0.18+

## v0.15.0 (2026-04-13)

**Discovery workflow glue — the "one wrapper, not six commands" release.**

Driven by a live end-to-end test of v0.14.0 that revealed 9 pain points between "I have a topic" and "I have a papers_input.json ready to ingest". This release fixes the highest-priority glue issues (shape bugs + command chain) in one track. Tracks B (backend dedup + confidence) and C (query intelligence) are deferred to v0.16+ pending a second live test.

### Added — `research-hub discover` wrapper

- **`src/research_hub/discover.py`** (new module, ~290 LOC) — stateful wrapper around search + fit-check that chains the two together with a pause at the AI-scoring handoff. State lives under `<vault>/.research_hub/discover/<cluster-slug>/` and is safe to delete.
- **`research-hub discover new --cluster X --query "..."`** — runs search internally, stashes candidates, writes the fit-check prompt to stdout or `--prompt-out file`. Supports `--year`, `--min-citations`, `--backend`, `--limit`, `--definition`.
- **`research-hub discover continue --cluster X --scored file.json`** — reads stashed candidates, runs fit-check apply (writes the existing `.fit_check_rejected.json` sidecar), converts accepted candidates into a correctly-shaped papers_input.json. Supports `--threshold N` (explicit) and `--auto-threshold` (uses `median(scores) - 1` clamped to `[2, 5]`).
- **`research-hub discover status --cluster X`** — shows current stage (`new` / `scored_pending` / `done`), candidate count, accepted/rejected counts.
- **`research-hub discover clean --cluster X`** — removes the stash directory, safe to run before re-discovering.

### Added — `--auto-threshold` for fit-check apply

- **`research-hub fit-check apply --auto-threshold`** computes threshold from score distribution (`median - 1` clamped to `[2, 5]`). Explicit `--threshold N` still wins when both are supplied. Useful for well-calibrated AI scoring where 5 = obvious accept, 3 = boundary case, 0-1 = obvious reject — the median-1 heuristic rejects boundary cases that the default threshold of 3 would keep.
- **`fit_check.compute_auto_threshold(scores)`** exposed as a reusable helper.

### Fixed — shape bugs from v0.13.0-A

- **`research-hub search --to-papers-input` emitted `{"papers": [...]}`** but the pipeline schema requires a flat JSON array. Now emits a flat list.
- **Authors were a comma-joined string** instead of the Zotero creator dicts the pipeline expects (`[{"creatorType":"author", "firstName":"...", "lastName":"..."}, ...]`). Now emits creator dicts via a shared `_authors_to_creators` helper.
- **Required-but-empty fields** (`summary`, `key_findings`, `methodology`, `relevance`) caused the pipeline validator to reject the output. Now filled with `[TODO: ...]` placeholder markers that the AI replaces in the next step.

These bugs meant v0.14.0's `--to-papers-input` output was unusable without a manual Python adapter script between `search` and `ingest`. v0.15.0 eliminates both adapter steps.

### MCP surface

- 4 new tools: `discover_new`, `discover_continue`, `discover_status`, `discover_clean` — **42 tools total** (was 38).

### Tests

- **560 → 581 passing** (+21 new tests, 5 skipped unchanged).
- `tests/test_discover.py`: 20 tests covering state management, continue logic, auto-threshold, status, clean, and a CLI end-to-end smoke test.
- Existing `test_cli_search.py` and `test_fit_check.py` updated for the new shapes.

### Non-breaking changes only

- `research-hub search --to-papers-input` output shape changed from `{"papers": [...]}` to a flat list. **This is technically a breaking change for any script that parsed the old (buggy) output.** But since the old shape was incompatible with the pipeline validator, it's unlikely any caller actually used it end-to-end.
- All existing CLI commands and MCP tool signatures continue to work unchanged.

### Deferred to v0.16+

- Cross-backend dedup (arxiv↔DOI pairs still double-count)
- SearchResult confidence scoring (which backends found each paper)
- Query generation from cluster definition
- Reject-reason failure analysis

## v0.14.0 (2026-04-13)

**Rigorous fit-check + sub-topic notes — the "know your papers are on-topic AND find them by theme" release.**

Two tracks shipped together. Track A adds a multi-gate fit-check system so you can catch off-topic papers BEFORE they pollute a cluster (instead of discovering it only after the 20-minute NotebookLM cycle). Track B adds sub-topic notes so you can browse a cluster by theme without flipping through every paper. Both tracks stay in the emit/apply pattern — research-hub never calls an LLM directly, the user's AI does the scoring and writing.

### Added — Track A: Multi-gate fit-check system

- **`src/research_hub/fit_check.py`** (328 LOC) — four gates validating cluster topic fit at every pipeline stage.
- **Gate 1 — Pre-ingest AI scoring.** `research-hub fit-check emit` builds a prompt asking an AI to score each candidate paper 0-5 against the cluster definition (falls back to parsing the overview's `## Definition` section when no `--definition` supplied). `research-hub fit-check apply` consumes the scored JSON, filters by threshold (default 3), and writes `.fit_check_rejected.json` sidecar for audit. Default threshold is 3 (keep score >= 3).
- **Gate 2 — Ingest-time term overlap.** Fast, no AI. Extracts up to 12 key terms from the cluster definition (4-char words, word-boundary matches, stoplist). Computes the fraction present in each paper's abstract. Zero overlap → paper frontmatter tagged `fit_warning: true` but still ingested (warning only, never blocks).
- **Gate 3 — Post-ingest NotebookLM audit.** `notebooklm/upload.py` briefing system prompt now requires a `### Off-topic papers` section in every generated briefing. `research-hub fit-check audit --cluster X` parses the section, writes `.fit_check_nlm_flags.json`, and exits 1 if any papers are flagged.
- **Gate 4 — Periodic drift check.** `research-hub fit-check drift` re-emits the fit-check prompt for already-ingested papers against the current overview. Reports only — never auto-removes.
- **CLI surface:**
  - `research-hub fit-check emit --cluster X --candidates file.json [--definition "..."]`
  - `research-hub fit-check apply --cluster X --candidates file.json --scored file.json [--threshold 3]`
  - `research-hub fit-check audit --cluster X`
  - `research-hub fit-check drift --cluster X`
  - `research-hub ingest --fit-check --fit-check-threshold 3` — opt-in gate at ingest time.
- **MCP surface:** 4 new tools — `fit_check_prompt`, `fit_check_apply`, `fit_check_audit`, `fit_check_drift` — **33 tools total** (was 29).

### Added — Track B: Sub-topic notes

- **`src/research_hub/topic.py`** extended with sub-topic propose/assign/build/list support. All v0.13.0 functions (`scaffold_overview`, `read_overview`, `get_topic_digest`, `hub_cluster_dir`, `overview_path`) remain unchanged. `topic.py` grew from 206 LOC to ~720 LOC.
- **File convention** — each cluster's `raw/<cluster>/` folder now has a `topics/` subfolder containing `NN_<slug>.md` files, one per sub-topic. Paper notes gain a `subtopics: [a, b]` frontmatter field. A paper can belong to multiple sub-topics.
- **Three-phase workflow:**
  - **Propose** (`research-hub topic propose --cluster X [--target-count 5]`) — emits a prompt asking an AI to propose 3-6 natural groupings from the cluster digest.
  - **Assign** — `research-hub topic assign emit --subtopics proposed.json` emits the per-paper mapping prompt. `research-hub topic assign apply --assignments file.json` writes the `subtopics:` frontmatter to each paper note.
  - **Build** (`research-hub topic build --cluster X`) — reads paper frontmatter, generates `topics/NN_<slug>.md` for each unique sub-topic. File numbering is stable across runs. Overwrites ONLY the `## Papers` section; Scope / Why / Open questions / See also are user-owned and preserved verbatim on re-run.
  - **List** (`research-hub topic list --cluster X`) — prints a table of existing sub-topics with paper counts.
- **Sub-topic template sections** — Scope / Why these papers cluster together / Papers (auto-generated) / Open questions / See also. Papers section uses Obsidian wiki-links: `[[<slug>|<short-title> (<lastname> <year>)]] — <one-line take>`.
- **MCP surface:** 5 new tools — `propose_subtopics`, `emit_assignment_prompt`, `apply_subtopic_assignments`, `build_topic_notes`, `list_topic_notes` — **38 tools total** (was 33 after Track A).
- **Dashboard integration** — `ClusterCard.subtopic_count` field, populated from `list_subtopics()`. Cluster card shows a `N subtopics` badge when count > 0 (hidden when 0 to avoid clutter).

### Fixed

- **CI MCP test failures (second occurrence).** The earlier `[mcp,dev]` fix in v0.13.0 was insufficient: the tests still used fastmcp's private `mcp._tool_manager._tools` API and the direct `imported_function.fn(...)` pattern, both of which break on fastmcp versions where the decorator does not wrap the imported name. Added `tests/_mcp_helpers.py` with `_list_mcp_tool_names(mcp)` and `_get_mcp_tool(mcp, name)` that try the public `mcp.get_tools()` / `mcp.get_tool(name)` (async) API first and fall back to the private path only for older versions. Replaced every private-API access in `test_consistency.py`, `test_mcp_add_paper.py`, `test_mcp_citation_graph.py`, `test_mcp_server.py`, `test_e2e_smoke.py`.

### Tests

- **520 → 560 passing** (+40 new tests, 5 skipped unchanged).
- Track A: 20 new tests in `tests/test_fit_check.py` covering all four gates (emit_prompt, apply_scores, term_overlap, parse_nlm_off_topic, drift_check, CLI integration).
- Track B: 20 new tests in `tests/test_topic_subtopics.py` + `tests/test_cli_operations.py` covering propose/assign/build/list, stable numbering, multi-sub-topic papers, Papers-section-only overwriting.

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and public topic.py functions continue to work unchanged. `--fit-check` and sub-topic features are opt-in — default v0.13.0 behavior preserved.

## v0.13.0 (2026-04-12)

**Model-agnostic paper discovery + topic overview notes — the "any AI can drive it" release.**

Two tracks shipped together. Track A replaces single-backend Semantic Scholar search with a three-backend fallback chain (OpenAlex + arXiv + Semantic Scholar) exposed through CLI + MCP, so Claude Code, Claude Desktop, Codex CLI, Gemini CLI, Cursor, Continue, Aider, and plain-shell pipelines all discover papers the same way. Track B adds topic overview notes — every cluster now has a designated `00_overview.md` that any AI can write by reading a cluster digest. Research-hub is pure plumbing; the AI does the writing.

### Added — Track A: Multi-backend paper search + enrich mode

- **`src/research_hub/search/` package** (was single `search.py`) — 7 modules, 759 LOC total. Three backends implementing the `SearchBackend` protocol (`name`, `search`, `get_paper`):
  - **`OpenAlexBackend`** — free, concept search, no API key. Reconstructs abstracts from OpenAlex's inverted index representation. Extracts `arxiv_id` from location metadata. Uses polite-pool `mailto` query param for higher rate limits.
  - **`ArxivBackend`** — Atom XML parsing (stdlib `xml.etree.ElementTree`). 3s throttle per arXiv policy. Client-side year filtering. Strips version suffixes from arxiv IDs.
  - **`SemanticScholarClient`** — existing logic refactored into the backend interface, `year_to` parameter added.
- **`search/fallback.py::search_papers()`** — multi-backend orchestrator. First backend to return a dedup key (normalized DOI → arxiv_id → title) wins the base record; subsequent backends fill empty fields (abstract, pdf_url, citation_count, venue). Backends that raise are logged at WARNING and skipped — never propagates. Results sorted by year descending then citation_count descending.
- **`search/enrich.py::enrich_candidates()`** — resolves a list of heterogeneous candidates (DOI / arxiv ID / title) to full `SearchResult` records. Title matches require rapidfuzz similarity ≥ 60. Purpose-built for Claude Code's WebSearch path: WebSearch discovers candidates, `enrich_candidates` turns them into ingest-ready records using OpenAlex/arXiv/Semantic Scholar.
- **CLI surface:**
  - `research-hub search "..." --year 2024-2025 --min-citations 10 --backend openalex,arxiv --json` — multi-backend query with year window, citation floor, and JSON output for piping.
  - `research-hub search "..." --to-papers-input --cluster <slug>` — emits a ready-to-ingest `papers_input.json` document with empty summary/key_findings/methodology/relevance fields for the AI to fill.
  - `research-hub enrich [candidates...] | -` — new subcommand. Reads DOIs / arxiv IDs / titles from argv or stdin, outputs enriched JSON.
  - `--year` parser accepts `2024`, `2024-`, `-2024`, and `2024-2025`.
- **MCP surface:**
  - `search_papers` extended with `year_from`, `year_to`, `min_citations`, `backends` parameters (backwards compatible — old signature still works).
  - `enrich_candidates(candidates, backends)` — new tool.
  - **26 MCP tools total** (was 25).
- **Backwards compat** — all existing `from research_hub.search import {SearchResult, SemanticScholarClient, iter_new_results}` imports still resolve through `search/__init__.py` re-exports. `iter_new_results` accepts both the legacy single-client signature and new multi-backend signature.

### Added — Track B: Topic overview notes

- **`src/research_hub/topic.py`** (206 LOC) — new module for AI-writable cluster summaries. Research-hub does NOT call any LLM; it provides a digest and a writing target, and the AI does the actual writing.
- **File convention** — overview lives at `<vault>/research_hub/hub/<cluster-slug>/00_overview.md`. The `00_` prefix floats it to the top of Obsidian's default alphabetical folder view.
- **Template sections** — Definition / Why it matters / Applications / Key sub-problems / Seed papers / Further reading. Scaffolded with frontmatter (`type: topic-overview`, `cluster: <slug>`, `status: draft`).
- **CLI surface:**
  - `research-hub topic scaffold --cluster <slug> [--force]` — writes the overview template file. Raises `FileExistsError` without `--force`.
  - `research-hub topic digest --cluster <slug> [--out file.md]` — emits the full-text digest of every paper in the cluster (title + authors + year + DOI + abstract) as markdown. The AI reads this to write the overview.
  - `research-hub topic show --cluster <slug>` — prints the current overview content, or exits 1 with a "no overview" hint.
- **MCP tools (3 new, 29 tools total)**:
  - `get_topic_digest(cluster_slug)` — returns `{cluster_slug, cluster_title, paper_count, papers: [...], markdown}`.
  - `write_topic_overview(cluster_slug, markdown, overwrite=False)` — writes AI-generated markdown. Refuses to overwrite without explicit flag.
  - `read_topic_overview(cluster_slug)` — returns `{ok, markdown}` or `{ok: False, reason: "no overview found"}`.
- **Dashboard integration** — `ClusterCard.has_overview` field, populated from `overview_path().exists()`. Cluster card shows "overview" / "no overview" badge; heading links to Obsidian's `00_overview.md` when present.
- **Vault builder integration** — when rendering the cluster hub/index page, prepends the overview content (frontmatter + first H1 stripped) above the paper list, so the Obsidian hub page opens with the topic summary.

### Added — Docs

- **`docs/ai-integrations.md`** — complete integration guide for Claude Code, Claude Desktop, Cursor, Continue, Codex CLI, Gemini CLI, Aider, and plain-shell workflows. Shows the exact commands for each AI surface. Covers the shared `discover → enrich → ingest → overview → verify via NotebookLM` pattern.

### Fixed

- **CI MCP test failures** — `.github/workflows/ci.yml` now installs `[mcp,dev]` extras. Without fastmcp the `_FallbackMCP` was returning raw functions with no `.fn` attribute, breaking `test_mcp_add_paper`, `test_e2e_smoke::test_e2e_mcp_download_artifacts_tool`, and `test_e2e_smoke::test_e2e_read_briefing_missing_returns_remedy`.

### Tests

- **465 → 520 passing** (+55 tests, 5 skipped unchanged).
- Track A: 40 new tests — `test_openalex_backend` (7), `test_arxiv_backend` (6), `test_search_fallback` (7), `test_search_enrich` (5), `test_cli_search` (6), `test_mcp_server` additions (3), `test_search.py` dedup_key + backcompat (6).
- Track B: 15 new tests — `test_topic` (12), `test_cli_operations` topic tests (3).

### Non-breaking changes only

All existing CLI commands, MCP tool signatures, and import paths continue to work unchanged. The `search.py` module is deleted and replaced by the `search/` package, but the public re-exports make this invisible to callers.

## v0.12.0 (2026-04-13)

**Pipeline hardening + PDF-first NotebookLM bundling + Draft composer — the "vault → draft" transition release.**

Three tracks shipped together, driven by real user-pain caught during a live 22-paper ingest of an LLM harness engineering cluster.

### Added — Track A: Pipeline hardening

- **Full schema validator** — `_validate_paper_input` now checks all 12 required fields upfront (was 4 in v0.11.0). Missing fields are reported with the exact text to paste into `papers_input.json`. Prevents the "KeyError mid-ingest → orphaned Zotero item" failure mode.
- **`slug` + `sub_category` auto-generation** — minimal papers_input.json entries (4 fields) now work out of the box. Slug is derived from `{firstauthor_lastname}{year}-{slugified_title}`; `sub_category` defaults to the cluster slug.
- **Collection-scoped `check_duplicate`** — `zotero/client.py::check_duplicate` gains optional `collection_key` kwarg. Library-wide search was producing false-positive skips when a paper existed in a different cluster's collection. New CLI flag `research-hub ingest --allow-library-duplicates` explicitly bypasses the dedup check.
- **`research-hub pipeline repair --cluster X`** — new subcommand that reconciles Zotero collection ⇄ Obsidian notes ⇄ dedup_index for a given cluster. Finds orphaned Zotero items (no Obsidian note), orphaned notes (no Zotero item), and stale dedup entries. Default dry-run; requires `--execute` to actually write.
- **`docs/papers_input_schema.md`** — rewritten with the full field reference, minimal + complete examples, and common-errors section.

### Added — Track B: PDF-first NotebookLM bundling

- **`research-hub notebooklm bundle --download-pdfs`** — new flag that tries to acquire a local PDF before falling back to URL upload. NotebookLM ingests local PDFs ~6× faster than URLs (it has to fetch + parse URLs server-side at 15-30s each).
- **`notebooklm/pdf_fetcher.py`** — new module with a 4-step fallback chain:
  1. Local cache by DOI (`<pdfs_dir>/<normalized_doi>.pdf`)
  2. Local cache by slug (`<pdfs_dir>/<slug>.pdf`)
  3. arXiv (`https://arxiv.org/pdf/<arxiv_id>.pdf` when the DOI is arxiv)
  4. Unpaywall API (free tier, OA-only papers)
- **Graceful handling of non-downloadable papers** — paywalled without OA, reports, timeouts, and oversized (>50 MB) PDFs all fall through to URL upload without erroring out. `BundleEntry.pdf_source` records provenance for the summary (`local-doi`, `arxiv`, `unpaywall`, etc).
- **Bundle summary** now breaks down by PDF source: `pdf: 22 (arxiv: 19, local-doi: 3, unpaywall: 0)`.

### Added — Track C: Draft composer

- **`research-hub compose-draft --cluster X --outline "Intro;Methods;Results" --style apa`** — new CLI that assembles captured quotes into a markdown draft. Supports APA / Chicago / MLA / LaTeX citation styles. Quotes are assigned to sections by matching `quote.context_note` against outline entries (case-insensitive substring); unmatched quotes land in the first section. Default output path: `<vault>/drafts/<YYYYMMDD>-<cluster>-draft.md`.
- **`src/research_hub/drafting.py`** — new module with `DraftRequest`, `DraftResult`, `compose_draft()`, `compose_draft_from_cli()`, and `DraftingError`. Reuses existing `writing.py` functions (`load_all_quotes`, `build_inline_citation`, `build_markdown_citation`, `resolve_paper_meta`) — no duplication.
- **MCP tool `compose_draft(cluster_slug, outline, quote_slugs, style, include_bibliography)`** — lets AI agents assemble drafts programmatically. Returns `{status, path, cluster_slug, quote_count, cited_paper_count, section_count, markdown_preview}`. **25 MCP tools total** (was 24).
- **Dashboard Writing tab composer panel** — new right column at >=900px: cluster picker, outline textarea, style radios, include-bibliography checkbox, quote multi-select (tied to left-column cards), and a `[Build draft command]` button that emits the exact `research-hub compose-draft ...` invocation and copies it to clipboard (same pattern as Manage tab).

### Changed

- NotebookLM briefing language note: briefings are generated in the language of the Google account's UI locale. To get English briefings for English users, set the Google account language to English before generating. A dedicated `research-hub briefings translate` feature is deferred to v0.13.

### Tests

- **417 → 465 passing** + 5 skipped. 48 new tests across the three tracks:
  - 30+ in `test_pipeline_schema_v012.py`, `test_pipeline_repair.py`, and updated `test_pipeline_metadata.py` / `test_pipeline.py`
  - 21 in `test_pdf_fetcher.py` + updated `test_notebooklm_bundle.py`
  - 22 in `test_drafting.py`, `test_dashboard_sections_v2.py`, `test_mcp_server.py`, `test_consistency.py`

## v0.11.0 (2026-04-12)

**Writing helpers — inline citations, quote capture, and a Writing tab to close the loop from "found it" to "used it in a draft".**

### Added
- **`research-hub cite --inline`** — emits an inline-style citation like `(Lamparth et al., 2024)` instead of full BibTeX. Useful in draft prose.
- **`research-hub cite --markdown`** — emits a markdown link with the DOI: `[Lamparth et al. (2024)](https://doi.org/10.1609/aies.v7i1.31681)`.
- **`research-hub cite --style apa|chicago|mla|latex`** — picks the inline format. APA is default. LaTeX style derives a BibKey from the paper slug (`\citep{lamparth2024human}`).
- **`research-hub quote <slug> --page 12 --text "..."` + `--context "..."`** — captures an excerpt from a paper into `<vault>/.research_hub/quotes/<slug>.md` with a small frontmatter block per quote (page, captured_at, context_note).
- **`research-hub quote list [--cluster SLUG]`** — browse captured quotes.
- **Dashboard Library tab** — every paper row now has a `[Quote]` button next to `[Cite]`. Clicking opens a popup with page + text + context fields and builds the exact `research-hub quote ...` command for you.
- **New Dashboard tab: Writing** (order 35, between Briefings and Diagnostics) — lists captured quotes grouped by cluster and papers marked `status: cited`. Each quote card has `Copy as markdown` and `Copy inline` action buttons.
- 3 new MCP tools (24 total):
  - `build_citation(doi_or_slug, style)` — returns `{inline, markdown}` for a paper so AI agents can build citations for your draft
  - `list_quotes(cluster_slug)` — lists captured quotes
  - `capture_quote(slug, page, text, context)` — saves a quote from the agent side
- **New module `src/research_hub/writing.py`** — holds the citation formatters, `Quote` dataclass persistence, and `resolve_paper_meta` helper that reads an Obsidian note's frontmatter to pull authors/year/title/doi.
- **New section module `src/research_hub/dashboard/writing_section.py`** — the Writing tab renderer.

### Changed
- Dashboard `DashboardData` now carries a `quotes: list[Quote]` field populated from `<vault>/.research_hub/quotes/*.md` on each render.
- `SKILL.md` documents the new `quote`, `cite --inline`, `cite --markdown`, and dashboard Writing tab.

### Tests
- Suite: **386 → 417 passing** + 5 skipped.
- 12 new tests in `tests/test_writing.py` covering the inline/markdown formatters, quote persistence (save + load + multi-block files), and frontmatter resolver.
- 7 new tests in `tests/test_dashboard_sections_v2.py` for the Writing section (empty state, quote cards, grouping by cluster, cited paper listing).
- Updated `test_header_section_renders_tabs` to expect the 6th tab radio.

## v0.10.0 (2026-04-12)

**Dashboard redesign — "personal knowledge garden" for AI-assisted literature review.**

The dashboard now answers a single question: *"AI added a bunch of papers — what did it add, what categories, and where is each one stored across Zotero / Obsidian / NotebookLM?"*

### Added
- **Five-tab audit dashboard** (`Overview` / `Library` / `Briefings` / `Diagnostics` / `Manage`). Pure CSS tabs (radio + `:checked` sibling selectors) — zero JavaScript for the tab mechanic. Default tab is Overview.
- **Overview tab** — three widgets:
  - **Treemap** of papers per cluster, sqrt-scaled flex weights so a 7/8/331 distribution stays readable (cluster names no longer get squeezed). Click any cell to jump to that cluster in the Library tab.
  - **Storage map** — per-cluster table with clickable `↗ Open` deep-links to each of the three systems: `zotero://select/library/collections/{key}`, `obsidian://open?path=raw/{slug}`, and the cluster's NotebookLM notebook URL.
  - **Recent additions** feed — last 15 papers your AI agent ingested, each with a cluster tag, relative time, and inline [Open] menu.
- **Library tab** — cluster cards with paper rows (title, authors, year, 240-char abstract, [Cite] popup, [Open ▼] menu). Per-cluster [Download .bib] button for batch citation export. NO status badges, NO reading-status pills — this is a locator, not a progress tracker.
- **Briefings tab** — inline preview of downloaded NotebookLM briefings with [Open in NotebookLM] and [Copy full text] actions.
- **Diagnostics tab** — health badges (Zotero / Obsidian / NotebookLM) + drift alerts + clickable remedy commands.
- **Manage tab** — per-cluster command-builder forms: rename, merge, split, bind-Zotero, bind-NLM, delete. Each form emits the exact `research-hub clusters …` CLI command on click and copies it to your clipboard.
- **Debug widget** — footer section with a "Copy snapshot" button that emits vault metadata + health state + cluster bindings as a paste-ready blob for AI assistant handoff. Closes the user feedback loop when something breaks.
- **Health banner** — when `doctor` reports any FAIL, the Overview tab shows a red banner at the top with the failing checks and their remedy commands.
- **`--watch` mode** — `research-hub dashboard --watch` polls vault state files every 5s and re-renders on change. Combine with `--refresh N` to control the browser auto-reload interval.
- **`--rich-bibtex` flag** — opt-in Zotero `get_formatted` per paper for full BibTeX entries (abstract, tags, collections). Default uses an instant frontmatter fallback — generation is under a second on a 346-paper vault.
- **Impeccable design tokens** — OKLCH-only color palette, warm-amber brand hue (not default blue), tinted neutrals, 4pt spacing scale, Geist/Literata/Geist Mono typography stack. Light theme.

### Changed
- Dashboard package now split into 6 modules: `types.py` (dataclass contract), `data.py` (vault walker), `citation.py`, `drift.py`, `briefing.py`, `sections.py`, `render.py`, plus inline `template.html` / `style.css` / `script.js`. Extensible via the `DashboardSection` base class.
- Dashboard render time on the 346-paper live vault: **0.9 seconds** (was 10+ minutes when the rich-BibTeX path was the default).
- Zotero credential loader now supports three file layouts: flat keys, nested `zotero.*` block, and the legacy `~/.claude/skills/zotero-skills/config.json` left over from the standalone zotero-skills install. Users who set up Zotero months ago no longer need to re-init.
- `doctor` routes all Zotero credential reads through the shared `_load_credentials()` helper so the health check sees exactly the same keys as the dashboard and the pipeline.
- Dashboard no longer renders per-paper Z/O/N sync badges or reading-status pills — they were fighting Zotero/Obsidian for the same real estate. Cross-system state is shown at the cluster level in the Storage map instead.

### Fixed
- **Chrome file:// security violation.** The Manage tab forms had no `action` attribute, so pressing Enter in an input field submitted to the current URL — which on `file://` triggers Chrome's "unsafe attempt to load URL from frame" block. Forms now carry `action="javascript:void(0)"` and the script.js submit handler routes Enter to the "Copy command" button.
- **Same security violation from treemap cells** — they used `<a href="#tab-library">`, which also trips the file:// check. Replaced with `<button data-jump-tab="library">` + a click handler that selects the target tab radio without navigating the URL.
- **331 missing [Cite] buttons** — `citation.py` caught the Zotero API error and returned `""` instead of falling through to the frontmatter fallback. Now every paper gets a valid BibTeX entry regardless of API availability.
- **Tab panels rendering blank** — CSS `:checked ~ main #tab-*` sibling selector was wrong because the radios are inside `<main>`, not siblings of it. Replaced with `:checked ~ #tab-*` direct sibling.
- **Treemap label overflow** for long cluster names. Added `-webkit-line-clamp: 3`, bumped min-width 140 → 200px and min-height 90 → 140px.
- `_detect_persona` no longer forces `analyst` when `zot=None` — persona is a config-time setting, not derived from runtime client state.
- `generate_dashboard` now instantiates `ZoteroDualClient` (has `get_formatted`) instead of the raw pyzotero `Zotero` object when the api_key is actually loadable.

### Tests
- Suite: **361 → 386 passing** (5 legacy v0.9.0-G1 section tests marked as `@pytest.mark.skip("rewritten in v0.10")`).
- 14 new tests for the dashboard data layer (`tests/test_dashboard_data.py`).
- 23 new tests for the dashboard sections layer (`tests/test_dashboard_sections_v2.py`).

## v0.9.0 (2026-04-12)

**System integration audit + UX hardening + personal HTML dashboard + closes the AI loop with NotebookLM artifact download.**

### Added
- `research-hub notebooklm download --cluster X --type brief` — downloads the latest generated briefing from NotebookLM back to `<vault>/.research_hub/artifacts/<cluster>/brief-<UTC>.txt`. Reads `span.notebook-summary .summary-content` from the DOM directly (no clipboard juggling, locale-independent). **Closes the AI loop**: search → save → upload → generate → **download** → AI analysis.
- `research-hub notebooklm read-briefing --cluster X` — prints the most recently downloaded briefing for inline AI analysis.
- 2 new MCP tools: `download_artifacts(cluster_slug, artifact_type)`, `read_briefing(cluster_slug)` — let AI agents pull briefings into context without re-running NotebookLM.
- `research-hub dashboard [--open]` — personal HTML dashboard at `<vault>/.research_hub/dashboard.html`. Single self-contained file with stat cards, cluster table, status badges, and NotebookLM links. Hero artifact for the project.
- `research-hub add <doi-or-arxiv-id> [--cluster X]` — one-shot Search → Save replaces hand-writing `papers_input.json`. Fetches metadata via Semantic Scholar with CrossRef enrichment.
- `research-hub init --persona researcher|analyst` — analyst persona skips Zotero entirely (Obsidian + NotebookLM only).
- `research-hub dedup invalidate --doi/--path` and `dedup rebuild [--obsidian-only]` — surgical dedup management without re-scanning Zotero.
- `papers_input.json` validator: pipeline catches missing `creatorType`, malformed authors, missing fields BEFORE hitting Zotero API. Clear error messages instead of cryptic 400 crashes.
- 4 new MCP tools total: `add_paper`, `generate_dashboard`, `download_artifacts`, `read_briefing` (21 total).
- New docs: `docs/cli-reference.md`, `docs/papers_input_schema.md`.

### Changed
- `doctor` now persona-aware: when `no_zotero: true` is set in config or `RESEARCH_HUB_NO_ZOTERO=1` env var, Zotero checks report "Skipped (analyst mode)" instead of FAIL.
- `doctor` correctly counts dedup index entries (was reporting 0 when index had thousands).
- `nlm_cache.json` now records `artifacts.brief = {path, downloaded_at, char_count, titles}` per cluster after a successful download.

### Fixed
- Pipeline silently dropped dict-format authors `[{firstName, lastName}]` → `authors: "Unknown"` in Obsidian YAML.
- Pipeline never wrote `volume`, `issue`, `pages` to Zotero or Obsidian even when input had them.
- `clusters rename` updates display name without orphaning notes.
- 12 new regression tests for pipeline metadata and dedup invalidation.
- 4 new tests for the briefing download / read flow (mocked CDP session).

Suite: 274 → 338 passing.

## v0.8.2 (2026-04-12)

### Added
- New MCP tool `propose_research_setup(topic)` — AI agents propose cluster/collection/notebook names BEFORE creating, ask user to confirm.
- `RESEARCH_HUB_NO_ZOTERO=1` env var enables data analyst persona (Obsidian + NotebookLM only, no Zotero).
- SKILL.md documents both personas + the "always confirm names" protocol.

## v0.8.1 (2026-04-12)

### Fixed
- `_render_obsidian_note` now handles dict-format authors (was producing `authors: "Unknown"`).
- Pipeline + `make_raw_md` now emit `volume`, `issue`, `pages` fields to both Zotero items and Obsidian YAML.
- New `**Citation:** Journal, Vol(Issue), Pages` line in note body.

## v0.8.0 (2026-04-12)

### Added
- Citation graph exploration via Semantic Scholar API.
- `research-hub references <doi>` — list papers cited by this paper.
- `research-hub cited-by <doi>` — list papers that cite this paper.
- 2 new MCP tools: `get_references`, `get_citations` (16 total).

## v0.7.0 (2026-04-12)

### Added
- Daily research operations: `remove`, `mark`, `move`, `find`.
- Cluster CRUD: `clusters rename`, `clusters delete`, `clusters merge`, `clusters split`.
- Vault search: `research-hub find "query" [--full] [--cluster X] [--status Y]`.
- 6 new MCP tools (14 total): `remove_paper`, `mark_paper`, `move_paper`, `search_vault`, `merge_clusters`, `split_cluster`.

## v0.6.0 (2026-04-12)

### Added
- MCP stdio server for AI assistant integration. 8 tools exposed via `research-hub serve`.
- Tools: `search_papers`, `verify_paper`, `suggest_integration`, `list_clusters`, `show_cluster`, `export_citation`, `run_doctor`, `get_config_info`.
- Optional dependency `[mcp]` extra installs `fastmcp>=2.0`.

## v0.5.0 (2026-04-12)

**First public PyPI release.** `pip install research-hub-pipeline[playwright]`

### Added
- `research-hub init` — interactive setup wizard (vault + Zotero + Chrome)
- `research-hub doctor` — 7-check health diagnostic
- `research-hub install --platform X` — skill install for Claude Code / Codex / Cursor / Gemini CLI
- `research-hub verify --doi/--arxiv/--paper` — HTTP-based paper existence verification with 7-day cache
- `research-hub suggest <id> [--json]` — cluster + related-paper suggestions (keyword/tag/author/venue scoring)
- `research-hub cite <id> --format bibtex` — BibTeX / BibLaTeX / RIS / CSL-JSON export via pyzotero
- `research-hub notebooklm login --cdp` — CDP-attach login bypassing Google bot detection
- `research-hub notebooklm upload --cluster X` — auto-upload PDF + URL sources
- `research-hub notebooklm generate --type brief` — trigger NotebookLM artifact generation (fire-and-forget)
- NotebookLM selectors verified against live zh-TW DOM (2026-04-11)
- Bundle builder: author-year PDF filename matching fallback
- platformdirs config resolution (Linux XDG / macOS / Windows APPDATA)
- GitHub Actions: CI (3.10/3.11/3.12) + auto-publish to PyPI on tag push
- SKILL.md bundled in wheel for AI coding assistant discoverability
- Terminal output examples at `docs/examples/`

### Changed
- Package name: `research-hub` → `research-hub-pipeline` (PyPI)
- Config path: repo-local → `platformdirs.user_config_dir("research-hub")`
- `verify` subcommand: extended with `--doi/--arxiv/--paper` flags (repo-integrity check preserved as fallback)
- Pipeline DOI validation: replaced `"48550" in doi` heuristic with real HTTP HEAD checks
- `upload_cluster` + `generate_artifact`: default `headless=False` (visible Chrome)
- README: rewritten for pip-install-first audience (310 lines)

### Fixed
- `Path(__file__).parents[N]` repo-relative paths crash after pip install
- NotebookLM selectors: `source-stretched-button` → `add-source-button`, `source-panel` → `source-picker`
- Bundle builder: 0 PDFs when vault uses Author_Year filenames
- `token_set_ratio` threshold: 87 → 80 (cross-platform rapidfuzz compatibility)
- pytest-cov missing from dev dependencies

## v0.4.0 (2026-04-11)

### Added
- Tri-system cluster binding (Zotero + Obsidian + NotebookLM)
- `clusters bind/show/new/list` CLI
- `sync status/reconcile` for Zotero ↔ Obsidian drift
- `notebooklm bundle --cluster X` drag-drop fallback
- 142 tests

## v0.3.4 (2026-04-10)

### Added
- `research-hub status` dashboard
- `migrate-yaml` for legacy note patching
- Hub index overview page

## v0.3.0 — v0.3.3 (2026-04-10)

### Added
- Dedup index (DOI + title normalization)
- Topic clusters with seed keywords
- Bidirectional wikilink updater
- Cluster synthesis pages
- Semantic Scholar search stub

## v0.2.1 (2026-04-10)

### Added
- First public release (MIT license)
- Bilingual README (EN + zh-TW)
- CI on Python 3.10 / 3.11 / 3.12
