# Nandi Registry

The public index of agents and packs for the [Nandi](https://github.com/vaultdbai/nandi) marketplace. The Nandi app reads this repository (`github.com/vaultdbai/nandi-registry`) as its default registry. The registry only _describes_ agents. The agents themselves live in their publishers' own git repositories, and Nandi installs them from there at the pinned `ref`.

## Structure

```
index.json                 everything the app lists: { "schema_version": 1, "agents": [...], "packs": [...] }
agents/<agent-id>.json     one full agent entry
packs/<pack-id>.json       one full pack entry
publishers/<handle>.json   one publisher (GitHub handle, signing key once signing ships)
```

### Agent entry

```json
{
  "id": "arxiv-researcher",
  "name": "ArXiv Researcher",
  "description": "One sentence, at most 200 characters.",
  "publisher": "vaultdbai",
  "repo": "github.com/vaultdbai/nandi-research-pack",
  "path": "agents/arxiv-researcher",
  "latest_version": "1.0.0",
  "ref": "v1.0.0",
  "tags": ["research", "papers"],
  "min_nandi_version": "0.1.0",
  "capabilities": {
    "tools": ["shell", "read_file", "write_file", "list_dir"],
    "network": ["export.arxiv.org", "api.semanticscholar.org"],
    "pilots": [],
    "requires_approval": ["shell", "write_file"]
  },
  "estimated_cost_usd": { "min": 0.01, "max": 0.15 },
  "icon_url": "https://raw.githubusercontent.com/<owner>/<repo>/HEAD/icon.svg",
  "readme_url": "https://raw.githubusercontent.com/<owner>/<repo>/HEAD/agents/<id>/README.md"
}
```

### Pack entry

The same identity fields (without `path`), plus `agents` (`id`, `name`, `description` for each), `workflows` (IDs), `capabilities` (the union of its agents'), `install_size_kb`, `estimated_cost_usd` (per workflow run) and `icon_url`/`readme_url`.

### Rules the app enforces

- IDs: lowercase letters, digits and hyphens, at most 64 characters. Agent and workflow IDs must be unique across the whole registry, because a user can install everything at once.
- `path` is relative inside the repo, with no `..`. `ref` is a tag or branch (normally `v<latest_version>`).
- `icon_url` and `readme_url` must be `https://` (or relative).
- `capabilities` must match the agent's `skill.md` exactly: `tools` = `allowed-tools`, `network` = the `network.allow` hosts, `requires_approval` = `requires_approval`. Nandi shows these to the user before install and enforces the `skill.md` values at run time. An entry that understates them is rejected in review.
- Bad entries are skipped by the app with a log line; the rest of the index still loads.

## Submitting an agent or pack

1. **Publish your source repo.** It must be public and contain, for a single agent, a folder with `skill.md` (plus optional `instructions.md`, `README.md`, `workflows/*.yaml`); for a pack, `.nandi/manifest.yaml`, `agents/<id>/…` and `workflows/*.yaml`. Add a `LICENSE`. Tag the release: `git tag -a v1.0.0 -m v1.0.0 && git push --tags`.
2. **Fork this repository** and add:
   - `agents/<id>.json` for each agent, and/or `packs/<id>.json`
   - the same entries in `index.json` (in the `agents` / `packs` arrays)
   - `publishers/<your-github-handle>.json` if you're new: `{ "github_handle": "...", "public_key": null, "created_at": "<ISO 8601>" }`
3. **Open a pull request.** Reviewers check that:
   - the repo, `path` and `ref` resolve, and the files at that ref match the entry (IDs, names, capabilities)
   - the system prompt is genuinely useful and doesn't ask for capabilities it doesn't use
   - network hosts are specific (no `*`) and justified in the agent's README
   - every tool that can write files or run commands requires approval, unless there's a good reason it doesn't
   - IDs don't collide with existing entries
4. **To release an update,** tag a new version in your repo and open a PR bumping `latest_version` and `ref` (and anything else that changed). Nandi never updates installs automatically. Users see the update and apply it themselves.

The vaultdbai packs are built from one content folder with `tools/build_index.py`, which regenerates `index.json` and the derived fields from the packs' `skill.md` files so the registry can't drift from the content. You're welcome to use the same approach for your own entries.

## Community and private registries

Any git repo (or static host, or local `file://` folder) with this exact layout is a registry. To use one, add it to `marketplace.registries` in Nandi's `settings.yaml` (or through the app's add-registry command):

```yaml
marketplace:
  registries:
    - url: github.com/vaultdbai/nandi-registry # keep the default public registry
      kind: public
    - url: github.com/acme/nandi-community-acme
      kind: community
    - url: github.com/acme/private-agents
      kind: personal
      auth: nandi.marketplace.acme # keyring entry holding a GitHub token
```

If the key is absent, only this public registry is used. If you list registries yourself, include this one too if you still want it. Nandi merges every configured registry: when two list the same ID, the higher `latest_version` wins, and a tie goes to the registry listed first.

- **Community registry:** fork this repo (or start an empty one with the same folders), add your entries, and share the repo URL.
- **Private registry:** a private repo works too. Its token lives in your OS keyring; `settings.yaml` holds only the keyring reference (`auth`). `auth: nandi.github.token` means "use the signed-in GitHub account".
- Caching: Nandi re-checks the public registry hourly, community registries every 15 minutes and personal ones every 5 minutes, using ETags. A rate-limited or offline registry falls back to its cached copy.

## License

The registry metadata is MIT licensed. Each listed agent is licensed by its own repository.
