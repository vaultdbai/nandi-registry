# AI Agent Instructions

## Overview

The Nandi registry (MIT): the public index of agents and packs the Nandi app reads as its default registry. It only _describes_ agents. The agents live in their publishers' git repos, and Nandi installs them from there at the pinned `ref`. Structure, entry formats and the submission steps are in [README.md](README.md).

Inside the Nandi workspace, the workspace `AGENTS.md` adds the general standards. This file is the stand-alone minimum for contributors.

## Core Rules (CRITICAL)

- **The entry rules the app enforces** are in "Rules the app enforces" in `README.md`: IDs, relative `path` with no `..`, `ref`, `https://` URLs, and `capabilities` that match the agent's `skill.md` exactly. Follow them, or the app skips the entry.
- **Review every entry** against the checklist in "Submitting an agent or pack" in `README.md`.
- **Keep `index.json` in step** with `agents/` and `packs/`. Pin each pack by its `ref` (normally `v<latest_version>`).
- **Sign the pack and every agent entry.** An unsigned agent entry fails the app's starter pack install.
- **Match each file's stored line ending.** `tools/build_index.py` writes CRLF on Windows; check `git diff` before committing and keep the ending the file already has.
- **Build releases with only published packs next to the registry.** `tools/build_index.py` indexes every sibling folder that has `.nandi/manifest.yaml`, so an unpublished pack cloned beside it leaks into `index.json`.
- No unsolicited commits, and never force-push. Use Conventional Commits.

## Build and Check

```bash
python tools/build_index.py --check   # validate, and fail if the index is out of date
python tools/build_index.py           # regenerate the derived fields
```

## Licence

The registry metadata is MIT (see `LICENSE`). Each listed agent is licensed by its own repository.
