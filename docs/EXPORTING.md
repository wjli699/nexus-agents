# Exporting n8n Workflows for Version Control

n8n stores workflows in its database (Postgres, in this setup) — not as
files — so they aren't tracked by git automatically. Export them
periodically so your workflow logic has real history.

## Manual export (quick, via UI)

1. Open the workflow in the n8n editor
2. Use the menu (⋯ or top-right options) → **Download**
3. Save the resulting `.json` file into `workflows/` in this repo, named
   descriptively (e.g. `stock-agent.json`)
4. Commit it

## CLI export (better for regular snapshots)

```bash
docker compose exec n8n n8n export:workflow --all --output=/tmp/workflows
docker cp $(docker compose ps -q n8n):/tmp/workflows ./workflows
```

This dumps every workflow as individual JSON files. Review the diff before
committing — n8n export JSON includes node positions and IDs, so diffs can
be noisier than the actual logical change; that's normal.

## What NOT to commit

- Credentials are stored encrypted in n8n's database and are **not**
  included in a workflow export by default — good, keep it that way.
  Never paste raw API keys/tokens into workflow JSON, node parameters, or
  this repo. Use n8n's credential store, referenced by name only.
- `.env` (already gitignored) — this holds your actual secrets locally.

## Suggested cadence

Export after any meaningful change to a workflow (new node, changed logic,
new branch) — treat it like committing code, not just a backup taken
occasionally.
