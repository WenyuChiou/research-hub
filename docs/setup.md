# Setup guide

Step-by-step first-time install for Research Hub v0.2.1. Expected total time: 20–40 minutes, depending on how many of the dependencies you already have.

---

## Prerequisites checklist

Before starting, confirm you have or can obtain:

- [ ] Python 3.10, 3.11, or 3.12
- [ ] Zotero Desktop (free)
- [ ] A Zotero account (free) and Web API key
- [ ] An Obsidian vault (you can create one during setup)
- [ ] Claude Code installed and authenticated
- [ ] Optional: a Google account for NotebookLM

---

## Step 1 — Install Python and the package

```bash
git clone https://github.com/WenyuChiou/research-hub
cd research-hub
pip install -e '.[dev]'
```

The `-e` flag installs in editable mode so edits to `src/` take effect without reinstalling. The `[dev]` extra pulls in `pytest`, `pytest-mock`, `responses`, and `pytest-cov` so the test suite runs.

Verify the install:

```bash
python -c "import research_hub; print(research_hub.__file__)"
pytest -q
```

You should see 42 tests pass.

---

## Step 2 — Set up Zotero

### 2a. Install Zotero Desktop

Download from <https://www.zotero.org/download/> and run the installer. Launch Zotero at least once so it creates the local database.

### 2b. Enable the local API

Zotero exposes a read-only REST API on `localhost:23119` when the "allow other applications" preference is on.

1. Open Zotero Desktop
2. Settings → Advanced → Config Editor
3. Search for `extensions.zotero.httpServer.enabled`
4. Set it to `true`
5. Restart Zotero

Test:

```bash
curl http://localhost:23119/api/users/0/items?limit=1
```

It should return some JSON (error about user 0 is fine — the endpoint is reachable).

### 2c. Get a Web API key

The local API is read-only. Writes (creating items, adding notes) go through the Zotero Web API, which needs a personal key.

1. Go to <https://www.zotero.org/settings/keys>
2. Click "Create new private key"
3. Give it a name like "research-hub"
4. Enable: "Allow library access" and "Allow write access"
5. Save the key somewhere safe — you'll need it in Step 4

### 2d. Find your library ID

On the same page (<https://www.zotero.org/settings/keys>), under "Your userID for use in API calls", copy the numeric ID. This is your `library_id`.

---

## Step 3 — Set up an Obsidian vault

If you already have a vault you want to use, skip to Step 4 and note its root path.

Otherwise:

1. Install Obsidian from <https://obsidian.md/>
2. Create a new vault. The folder where the vault lives will be `knowledge_base.root`
3. Inside the vault, create these sub-folders (the pipeline will write to them):
   - `raw/` — per-paper markdown notes
   - `hub/` — generated index pages
   - `logs/` — pipeline logs
4. Optional: install the Dataview plugin if you want to use the ready-made queries in `references/dataview-queries.md`

---

## Step 4 — Configure `config.json`

Copy the template and edit it:

```bash
cp config.json.example config.json
```

Open `config.json` and set at minimum these three keys:

```json
{
  "knowledge_base": {
    "root": "~/vault/research-hub"
  },
  "zotero": {
    "library_id": "1234567",
    "default_collection": "ABCD1234"
  }
}
```

- `knowledge_base.root` — absolute path (or `~` for home) to your Obsidian vault
- `zotero.library_id` — the numeric ID from Step 2d
- `zotero.default_collection` — a Zotero collection key that you've created in Zotero Desktop (create one via right-click → New Collection, then inspect the URL or use Zotero MCP to read the key)

Your API key goes in an environment variable, not `config.json`:

```bash
# Option A — set in your shell profile
export ZOTERO_API_KEY="your-key-here"

# Option B — use ~/.claude/.env (Claude Code reads this automatically)
echo 'ZOTERO_API_KEY=your-key-here' >> ~/.claude/.env
```

Never commit `config.json` — it is in `.gitignore`, but verify before pushing any fork.

See [docs/customization.md](customization.md) for the full schema and the `zotero.collections` map.

---

## Step 5 — Install Claude Code and MCP connectors

Research Hub is a Claude Code skill; you need Claude Code to run it.

1. Install Claude Code: follow <https://docs.claude.com/en/docs/claude-code>
2. Authenticate with your Anthropic account
3. Install the MCP connectors the pipeline uses:
   - `paper-search-mcp` — <https://github.com/openags/paper-search-mcp>
   - Zotero MCP — for read-only library inspection
   - Desktop Commander — ships with Claude Code

Each MCP server has its own install guide in its README. Add them to your `~/.claude/mcp.json` or equivalent.

---

## Step 6 — Install the `zotero-skills` sibling skill

Research Hub delegates all Zotero write operations to a separate skill. Install it:

```bash
cd ~/.claude/skills
git clone https://github.com/WenyuChiou/zotero-skills
```

The Research Hub skill references `zotero-skills` by path, so it must live in `~/.claude/skills/zotero-skills/`.

---

## Step 7 — (Optional) NotebookLM

Skip this step if you don't want the Step 5 upload to NotebookLM.

1. Go to <https://notebooklm.google.com/> and sign in
2. Create the notebooks you want the pipeline to upload into. Default names the skill expects (configurable):
   - `Research Hub Main`
   - `Research Hub Secondary`
3. Install the "Claude in Chrome" browser extension (or whatever Chrome automation Claude Code documents) so Claude can drive the upload

If you skip NotebookLM, the pipeline will run Steps 1–4 and 6–7 and silently skip Step 5.

---

## Step 8 — Verify

Run the setup checker:

```bash
python scripts/verify_setup.py
```

Expected output on success:

```
[ok] Python version: 3.11
[ok] research_hub package importable
[ok] config.json found at <path>
[ok] knowledge_base.root exists
[ok] zotero.library_id set
[warn] ZOTERO_API_KEY not set — writes will fail
[ok] Zotero local API reachable at localhost:23119
```

Fix any red lines before running the full pipeline for the first time.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Zotero local API not responding` | Start Zotero Desktop, then check `extensions.zotero.httpServer.enabled = true` in the Config Editor. Restart Zotero after toggling. |
| `Invalid library_id` or 403 on write | Cross-check the ID at <https://www.zotero.org/settings/keys> and confirm the API key has write access. |
| `import research_hub.zotero.fetch` hangs | Fixed in v0.2.1. If you're on an older commit, pull `master`. |
| Tests fail with `PermissionError` on Windows | Close any process holding files under `.pytest-work/` and rerun. `pytest.ini` already disables the cache provider to avoid this. |
| `NotebookLM upload blocked` or Chrome dialog stuck | Step 5 is fragile. Skip it by leaving `zotero.notebooklm.enabled = false` in config (planned in Phase 2; until then, comment out the upload call in `pipeline.py`). |
| `papers_input.json not found` during dry run | This is expected on a fresh install. `run_pipeline(dry_run=True)` returns 0 in that case. |
| `RuntimeError: Set zotero.default_collection` | Add the key to `config.json` (Step 4) or export `RESEARCH_HUB_DEFAULT_COLLECTION`. |
| Graph colors look wrong in Obsidian | Re-run `python -m research_hub.vault.categorize` and restart Obsidian. |

---

## Next steps

- Read [docs/customization.md](customization.md) to adapt the category system to your own research domain
- Read the skill body at `skills/knowledge-base/SKILL.md` to understand the 7-step pipeline in detail
- Run your first end-to-end flow: in Claude Code, say "add to Research Hub: <a topic you care about>"
