#!/usr/bin/env python3
"""Regenerate the Nandi registry from the pack folders, and validate everything.

Usage (from the marketplace-content folder or anywhere):

    python3 tools/build_index.py           # validate, then rewrite registry/ files
    python3 tools/build_index.py --check   # validate, and fail if registry/ is out of date

Derived from the packs (always overwritten):
    name, description, repo, path, version, ref, min_nandi_version, capabilities,
    agents/workflows lists, install_size_kb, icon_url, readme_url

Curated by hand in registry/agents/<id>.json and registry/packs/<id>.json (kept):
    tags, estimated_cost_usd, publisher, signature, and any other extra keys.
    SEED below is used only when an entry file doesn't exist yet.

Stdlib only, except PyYAML when it's installed (a minimal frontmatter parser is
the fallback). --check compares parsed JSON, so Prettier formatting is fine.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
# Two layouts: a workspace with registry/ and the pack folders side by side,
# or the nandi-registry repo itself (its root is the registry) with the pack
# repos (nandi-<id>) cloned next to it.
REGISTRY = ROOT / "registry" if (ROOT / "registry").is_dir() else ROOT
PACKS_ROOT = ROOT if REGISTRY != ROOT else ROOT.parent
PUBLISHER = "vaultdbai"
SCHEMA_VERSION = 1
RAW = "https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"

# pack folder -> GitHub repo name
PACK_REPOS = {
    "dev-pack": "nandi-dev-pack",
    "personal-backup": "nandi-personal-backup",
    "finance-pack": "nandi-finance-pack",
    "trading-pack": "nandi-trading-pack",
    "healthcare-pack": "nandi-healthcare-pack",
    "restaurant-pack": "nandi-restaurant-pack",
    "local-marketing-pack": "nandi-local-marketing-pack",
    "legal-pack": "nandi-legal-pack",
    "sales-pack": "nandi-sales-pack",
    "devops-pack": "nandi-devops-pack",
    "research-pack": "nandi-research-pack",
    "engineering-pack": "nandi-engineering-pack",
    "content-pack": "nandi-content-pack",
    "analytics-pack": "nandi-analytics-pack",
    "personal-pack": "nandi-personal-pack",
}

# Runtime tools plus the host-side built-ins an agent can be granted
KNOWN_TOOLS = {"shell", "read_file", "write_file", "list_dir", "delegate_to_agent", "find_people", "my_requests"}
ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# The keys the app accepts (src-tauri/src/services/domain/workflow.rs, Step and WorkflowFile)
STEP_KEYS = {
    "id",
    "step_type",
    "agent",
    "input",
    "instructions",
    "deadline_hours",
    "requires_approval",
    "critical",
    "on_failure",
}
WORKFLOW_KEYS = {"id", "name", "description", "steps", "provides"}
STEP_TYPES = ("agent", "manual")
TEMPLATE_RE = re.compile(r"\{\{\s*([^}]*?)\s*\}\}")
STEP_OUTPUT_RE = re.compile(r"^([A-Za-z0-9_.-]+?)\.output$")

SEED = {
    "agents": {
        "chief-of-staff": (["official", "personal", "productivity", "team"], 0.01, 0.10),
        "aws-ops-analyst": (["official", "ops", "aws", "incidents"], 0.02, 0.40),
        "pr-reviewer": (["official", "engineering", "code-review", "github"], 0.02, 0.40),
        "backup-keeper": (["official", "free", "personal", "backup", "aws"], 0.01, 0.05),
        "invoice-reconciler": (["finance", "invoices", "reconciliation", "accounting"], 0.01, 0.15),
        "cashflow-forecaster": (["finance", "cashflow", "runway", "treasury"], 0.02, 0.20),
        "financial-auditor": (["finance", "audit", "statements", "sec", "ratios"], 0.02, 0.25),
        "ar-collections": (["finance", "collections", "invoices", "receivables"], 0.01, 0.15),
        "market-sentiment-scout": (["trading", "sentiment", "news", "markets", "stocks"], 0.01, 0.20),
        "quant-backtester": (["trading", "quant", "backtesting", "python", "algorithmic"], 0.02, 0.30),
        "trade-journal-auditor": (["trading", "journal", "risk", "psychology", "discipline"], 0.01, 0.15),
        "portfolio-rebalancer": (["trading", "portfolio", "rebalancing", "allocation", "risk"], 0.01, 0.15),
        "soap-note-assistant": (["healthcare", "clinical", "soap", "medical", "notes"], 0.02, 0.25),
        "claim-denial-appealer": (["healthcare", "billing", "claims", "insurance", "appeals"], 0.02, 0.30),
        "patient-intake-triager": (["healthcare", "intake", "triage", "safety", "allergies"], 0.01, 0.20),
        "menu-margin-optimizer": (["restaurant", "menu", "food-cost", "pos", "pricing"], 0.02, 0.25),
        "inventory-waste-tracker": (["restaurant", "inventory", "waste", "par-levels", "kitchen"], 0.01, 0.20),
        "guest-review-responder": (["restaurant", "reviews", "reputation", "hospitality", "yelp"], 0.01, 0.15),
        "local-seo-optimizer": (["marketing", "local-seo", "google-business", "maps", "smb"], 0.01, 0.20),
        "promo-campaign-builder": (["marketing", "promotions", "sms", "email", "social"], 0.02, 0.25),
        "churn-winback-specialist": (["marketing", "retention", "win-back", "churn", "loyalty"], 0.01, 0.20),
        "contract-redliner": (["legal", "contracts", "redline", "agreements"], 0.02, 0.25),
        "agreement-abstractor": (["legal", "milestones", "deadlines", "sla"], 0.01, 0.15),
        "compliance-checker": (["legal", "privacy", "gdpr", "ccpa", "security"], 0.02, 0.25),
        "lead-researcher": (["sales", "research", "leads", "intelligence", "b2b"], 0.01, 0.20),
        "rfp-responder": (["sales", "rfp", "proposals", "bids", "security"], 0.02, 0.30),
        "outreach-drafter": (["sales", "email", "outreach", "copywriting"], 0.01, 0.15),
        "log-incident-analyzer": (["devops", "sre", "logs", "incidents", "debugging"], 0.02, 0.30),
        "cve-auditor": (["devops", "security", "cve", "dependencies", "vulnerabilities"], 0.02, 0.25),
        "api-spec-builder": (["devops", "api", "openapi", "typescript", "architecture"], 0.02, 0.20),
        "arxiv-researcher": (["research", "papers", "arxiv", "search"], 0.01, 0.15),
        "paper-summarizer": (["research", "papers", "summaries", "pdf"], 0.02, 0.30),
        "citation-formatter": (["research", "citations", "bibtex", "writing"], 0.01, 0.08),
        "code-reviewer": (["engineering", "code-review", "security", "git"], 0.02, 0.40),
        "test-writer": (["engineering", "testing", "quality"], 0.03, 0.50),
        "docs-generator": (["engineering", "documentation", "writing"], 0.02, 0.40),
        "pr-summarizer": (["engineering", "pull-requests", "git", "github"], 0.01, 0.15),
        "blog-draft-writer": (["content", "writing", "blogging", "marketing"], 0.02, 0.20),
        "newsletter-formatter": (["content", "newsletter", "email", "marketing"], 0.01, 0.12),
        "seo-analyzer": (["content", "seo", "marketing", "audit"], 0.01, 0.10),
        "data-fetcher": (["analytics", "data", "csv", "etl"], 0.01, 0.12),
        "chart-generator": (["analytics", "charts", "visualization"], 0.01, 0.12),
        "report-writer": (["analytics", "reporting", "kpis"], 0.02, 0.18),
        "email-triager": (["personal", "email", "productivity", "offline"], 0.01, 0.20),
        "calendar-summarizer": (["personal", "calendar", "productivity", "offline"], 0.01, 0.10),
        "meeting-notes": (["personal", "meetings", "notes", "productivity", "offline"], 0.01, 0.12),
    },
    "packs": {
        "dev-pack": (["official", "engineering", "productivity", "github", "aws"], 0.02, 0.40),
        "personal-backup": (["official", "free", "personal", "backup", "aws"], 0.01, 0.10),
        "finance-pack": (["finance", "accounting", "invoices", "cashflow", "smb", "corporate"], 0.05, 0.50),
        "trading-pack": (["trading", "markets", "stocks", "quant", "sentiment", "portfolio"], 0.05, 0.50),
        "healthcare-pack": (["healthcare", "clinical", "medical", "billing", "hipaa"], 0.05, 0.50),
        "restaurant-pack": (["restaurant", "hospitality", "menu", "inventory", "food-cost"], 0.05, 0.50),
        "local-marketing-pack": (["marketing", "smb", "local-seo", "promotions", "retention"], 0.05, 0.50),
        "legal-pack": (["legal", "contracts", "compliance", "procurement", "enterprise"], 0.05, 0.50),
        "sales-pack": (["sales", "gtm", "rfp", "leads", "outreach", "pipeline"], 0.05, 0.50),
        "devops-pack": (["devops", "sre", "security", "cve", "api", "reliability"], 0.05, 0.50),
        "research-pack": (["research", "papers", "citations", "academic"], 0.05, 0.60),
        "engineering-pack": (["engineering", "code-review", "testing", "documentation"], 0.08, 0.90),
        "content-pack": (["content", "writing", "seo", "newsletter"], 0.06, 0.50),
        "analytics-pack": (["analytics", "data", "charts", "reporting"], 0.05, 0.45),
        "personal-pack": (["personal", "productivity", "email", "calendar", "offline"], 0.04, 0.40),
    },
}

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


# -- Parsing -------------------------------------------------------------------


def split_frontmatter(text: str, where: str) -> tuple[str, str] | None:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.S)
    if not m:
        err(f"{where}: missing YAML frontmatter")
        return None
    return m.group(1), m.group(2)


def parse_yaml(text: str, where: str):
    if yaml is not None:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as e:
            err(f"{where}: invalid YAML: {e}")
            return None
    return minimal_yaml(text, where)


def _scalar(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if v in ("true", "false"):
        return v == "true"
    if v in ("", "null", "~"):
        return None
    return v


def minimal_yaml(text: str, where: str):
    """Just enough YAML for skill.md frontmatter and pack manifests:
    `key: scalar`, `key: [a, b]`, and one `network: {allow: [{host: ...}]}` block."""
    out: dict = {}
    current = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = raw.split(" #", 1)[0].rstrip()
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        if indent == 0:
            key, _, val = s.partition(":")
            out[key.strip()] = _scalar(val) if val.strip() else {}
            current = key.strip()
        elif current == "network":
            if s.startswith("allow:"):
                out["network"]["allow"] = []
            elif s.startswith("- host:"):
                out["network"]["allow"].append({"host": _scalar(s[len("- host:"):])})
            elif s.startswith("methods:"):
                out["network"]["allow"][-1]["methods"] = _scalar(s[len("methods:"):])
            else:
                err(f"{where}: minimal parser can't read '{s}' (install PyYAML)")
        else:
            err(f"{where}: minimal parser can't read '{s}' (install PyYAML)")
    return out


# -- Packs -------------------------------------------------------------------


def load_agent(pack: str, folder: Path) -> dict | None:
    agent_id = folder.name
    where = f"{pack}/agents/{agent_id}"
    if not ID_RE.match(agent_id):
        err(f"{where}: invalid agent ID")
    skill = folder / "skill.md"
    if not skill.is_file():
        err(f"{where}: skill.md missing")
        return None
    for extra in ("instructions.md", "README.md"):
        if not (folder / extra).is_file():
            err(f"{where}: {extra} missing")
    parts = split_frontmatter(skill.read_text(encoding="utf-8"), f"{where}/skill.md")
    if not parts:
        return None
    fm = parse_yaml(parts[0], f"{where}/skill.md")
    if not isinstance(fm, dict):
        err(f"{where}/skill.md: frontmatter is not a mapping")
        return None
    body = parts[1]

    name = fm.get("name")
    desc = fm.get("description") or ""
    if not isinstance(name, str) or not name.strip():
        err(f"{where}: name is required")
    if not isinstance(desc, str) or not desc or len(desc) > 200:
        err(f"{where}: description must be 1-200 chars (is {len(desc)})")
    for banned in ("model", "aws", "pilots"):
        if banned in fm:
            err(f"{where}: '{banned}' must not be set")
    unknown = set(fm) - {
        "name", "description", "allowed-tools", "requires_approval", "network", "connectors", "tags",
        "serves", "accepts_delegation",
    }
    if unknown:
        err(f"{where}: unexpected frontmatter keys {sorted(unknown)}")

    tools = fm.get("allowed-tools") or []
    approvals = fm.get("requires_approval") or []
    if not set(tools) <= KNOWN_TOOLS:
        err(f"{where}: unknown tools {sorted(set(tools) - KNOWN_TOOLS)}")
    if not set(approvals) <= set(tools):
        err(f"{where}: requires_approval lists tools not in allowed-tools")
    if "write_file" in tools and "write_file" not in approvals:
        err(f"{where}: write_file must require approval")
    if "shell" in tools and "shell" not in approvals:
        err(f"{where}: shell should require approval")
    if "delegate_to_agent" in tools and "delegate_to_agent" not in approvals:
        err(f"{where}: delegate_to_agent must require approval")

    hosts = []
    network = fm.get("network") or {}
    for rule in network.get("allow") or []:
        if not isinstance(rule, dict) or not rule.get("host"):
            err(f"{where}: network.allow entries need a host")
            continue
        if rule.get("methods"):
            err(f"{where}: host {rule['host']} has a methods limit (HTTPS tunnels need none)")
        hosts.append(str(rule["host"]).lower())

    # Connectors from Library › Tools, by ID (`[s3_backup]` or `[{id: filesystem, ...}]`)
    connectors = []
    for item in fm.get("connectors") or []:
        cid = item.get("id") if isinstance(item, dict) else item
        if not isinstance(cid, str) or not cid.strip():
            err(f"{where}: connectors entries need an id")
            continue
        if cid not in connectors:
            connectors.append(cid)

    words = len(re.findall(r"\S+", body))
    if not 300 <= words <= 900:
        err(f"{where}: system prompt is {words} words (want 300-900)")

    return {
        "id": agent_id,
        "name": name,
        "description": desc,
        "tools": list(tools),
        "network": hosts,
        "requires_approval": list(approvals),
        "connectors": connectors,
        "words": words,
    }


def load_workflow(pack: str, path: Path, agent_ids: set[str]) -> str | None:
    where = f"{pack}/workflows/{path.name}"
    data = parse_yaml(path.read_text(encoding="utf-8"), where) if yaml else None
    if yaml is None:
        print(f"note: PyYAML missing, skipping deep checks of {where}")
        return path.stem
    if not isinstance(data, dict):
        err(f"{where}: not a mapping")
        return None
    if set(data) - WORKFLOW_KEYS:
        err(f"{where}: unknown keys {sorted(set(data) - WORKFLOW_KEYS)}")
    wid = data.get("id")
    if wid != path.stem:
        err(f"{where}: id '{wid}' must equal the file name")
    if not isinstance(wid, str) or not WORKFLOW_ID_RE.match(wid):
        err(f"{where}: invalid workflow ID")
    if not data.get("name"):
        err(f"{where}: name is required")
    steps = data.get("steps") or []
    if not steps:
        err(f"{where}: no steps")
    seen: list[str] = []
    for i, step in enumerate(steps):
        sw = f"{where} step {i + 1}"
        if not isinstance(step, dict):
            err(f"{sw}: not a mapping")
            continue
        if set(step) - STEP_KEYS:
            err(f"{sw}: unknown keys {sorted(set(step) - STEP_KEYS)}")
        sid = step.get("id")
        if not isinstance(sid, str) or not WORKFLOW_ID_RE.match(sid) or sid in seen:
            err(f"{sw}: missing, invalid or duplicate step id '{sid}'")
        step_type = step.get("step_type", "agent")
        if step_type not in STEP_TYPES:
            err(f"{sw}: step_type must be agent or manual")
        if step_type == "manual":
            # A person follows the instructions; there's no agent or input
            text = step.get("instructions")
            if not isinstance(text, str) or not text.strip():
                err(f"{sw}: a manual step needs instructions")
                text = ""
            hours = step.get("deadline_hours")
            if hours is not None and (not isinstance(hours, int) or isinstance(hours, bool) or hours < 1):
                err(f"{sw}: deadline_hours must be a whole number of hours")
        else:
            if step.get("agent") not in agent_ids:
                err(f"{sw}: agent '{step.get('agent')}' is not in this pack")
            text = step.get("input")
            if not isinstance(text, str) or not text.strip():
                err(f"{sw}: input is required")
                text = ""
            for key in ("instructions", "deadline_hours"):
                if key in step:
                    err(f"{sw}: {key} is only for manual steps")
        for ref in TEMPLATE_RE.findall(text):
            m = STEP_OUTPUT_RE.match(ref)
            if not m:
                err(f"{sw}: unsupported template '{{{{{ref}}}}}'")
            elif m.group(1) not in seen:
                err(f"{sw}: '{{{{{ref}}}}}' is not an earlier step")
        for flag in ("requires_approval", "critical"):
            if flag in step and not isinstance(step[flag], bool):
                err(f"{sw}: {flag} must be true/false")
        if "on_failure" in step and step["on_failure"] not in ("fail", "continue"):
            err(f"{sw}: on_failure must be fail or continue")
        if isinstance(sid, str):
            seen.append(sid)
    return wid


# Contributor files at a pack repo's root: instructions for coding agents, not
# part of what the pack installs
REPO_ONLY_FILES = {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", ".gitignore"}


def folder_size_kb(folder: Path) -> int:
    # What the installer copies: not the repo's own .git folder
    total = sum(
        p.stat().st_size
        for p in folder.rglob("*")
        if p.is_file()
        and ".git" not in p.relative_to(folder).parts
        and not (p.parent == folder and p.name in REPO_ONLY_FILES)
    )
    return math.ceil(total / 1024)


def load_pack(folder: Path) -> dict | None:
    pack_id = folder.name.removeprefix("nandi-").removeprefix("nandi-")
    manifest_path = folder / ".nandi" / "manifest.yaml"
    if not manifest_path.is_file():
        err(f"{pack_id}: .nandi/manifest.yaml missing")
        return None
    manifest = parse_yaml(manifest_path.read_text(encoding="utf-8"), f"{pack_id}/manifest")
    if not isinstance(manifest, dict):
        return None
    if manifest.get("id") != pack_id:
        err(f"{pack_id}: manifest id '{manifest.get('id')}' must equal the folder name")
    for f in ("README.md", "LICENSE", "icon.svg"):
        if not (folder / f).is_file():
            err(f"{pack_id}: {f} missing")
    icon = folder / "icon.svg"
    if icon.is_file() and "currentColor" not in icon.read_text(encoding="utf-8"):
        err(f"{pack_id}: icon.svg should use currentColor")
    if len(manifest.get("description") or "") > 200:
        err(f"{pack_id}: manifest description over 200 chars")

    agent_folders = sorted(p for p in (folder / "agents").iterdir() if p.is_dir())
    agents = {a["id"]: a for a in (load_agent(pack_id, p) for p in agent_folders) if a}
    declared = manifest.get("agents") or []
    if sorted(declared) != sorted(p.name for p in agent_folders):
        err(f"{pack_id}: manifest agents {declared} don't match agents/ folders")

    wf_files = sorted((folder / "workflows").glob("*.yaml"))
    workflows = [w for w in (load_workflow(pack_id, p, set(agents)) for p in wf_files) if w]
    for p in agent_folders:  # optional agent-scoped workflows
        for wf in sorted((p / "workflows").glob("*.yaml")) if (p / "workflows").is_dir() else []:
            load_workflow(pack_id, wf, set(agents))
    if sorted(manifest.get("workflows") or []) != sorted(p.stem for p in wf_files):
        err(f"{pack_id}: manifest workflows don't match workflows/ files")

    return {
        "id": pack_id,
        "manifest": manifest,
        "agents": [agents[a] for a in declared if a in agents],
        "workflows": workflows,
        "size_kb": folder_size_kb(folder),
    }


# -- Registry ------------------------------------------------------------------


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(f"{path.relative_to(REGISTRY)}: invalid JSON: {e}")
        return None


def caps(agents: list[dict]) -> dict:
    def union(key: str) -> list[str]:
        out: list[str] = []
        for a in agents:
            out += [x for x in a[key] if x not in out]
        return out

    return {
        "tools": union("tools"),
        "network": union("network"),
        "pilots": [],
        "requires_approval": union("requires_approval"),
        "connectors": union("connectors"),
    }


def build(packs: list[dict]) -> dict[Path, dict]:
    files: dict[Path, dict] = {}
    index_agents, index_packs = [], []
    for pack in packs:
        m = pack["manifest"]
        repo_name = PACK_REPOS.get(pack["id"], f"nandi-{pack['id']}")
        repo = f"github.com/{PUBLISHER}/{repo_name}"
        raw = lambda p: RAW.format(owner=PUBLISHER, repo=repo_name, path=p)  # noqa: E731
        version = str(m["version"])
        common = {
            "publisher": PUBLISHER,
            "repo": repo,
            "latest_version": version,
            "ref": f"v{version}",
            "min_nandi_version": str(m.get("min_nandi_version", "0.0.0")),
        }
        for a in pack["agents"]:
            path = REGISTRY / "agents" / f"{a['id']}.json"
            old = read_json(path) or {}
            tags, lo, hi = SEED["agents"].get(a["id"], ([], 0.01, 0.10))
            entry = {
                "id": a["id"],
                "name": a["name"],
                "description": a["description"],
                **common,
                "publisher": old.get("publisher", PUBLISHER),
                "path": f"agents/{a['id']}",
                "tags": old.get("tags", tags),
                "capabilities": caps([a]),
                "estimated_cost_usd": old.get("estimated_cost_usd", {"min": lo, "max": hi}),
                "icon_url": raw("icon.svg"),
                "readme_url": raw(f"agents/{a['id']}/README.md"),
            }
            entry = {**old, **entry}
            files[path] = entry
            index_agents.append({k: v for k, v in entry.items() if k not in ("icon_url", "readme_url")})

        path = REGISTRY / "packs" / f"{pack['id']}.json"
        old = read_json(path) or {}
        tags, lo, hi = SEED["packs"].get(pack["id"], ([], 0.05, 0.50))
        entry = {
            "id": pack["id"],
            "name": m["name"],
            "description": m.get("description", ""),
            **common,
            "publisher": old.get("publisher", PUBLISHER),
            "tags": old.get("tags", tags),
            "agents": [
                {"id": a["id"], "name": a["name"], "description": a["description"]}
                for a in pack["agents"]
            ],
            "workflows": pack["workflows"],
            "capabilities": caps(pack["agents"]),
            "install_size_kb": pack["size_kb"],
            "estimated_cost_usd": old.get("estimated_cost_usd", {"min": lo, "max": hi}),
            "icon_url": raw("icon.svg"),
            "readme_url": raw("README.md"),
        }
        entry = {**old, **entry}
        files[path] = entry
        index_packs.append(entry)

    files[REGISTRY / "index.json"] = {
        "schema_version": SCHEMA_VERSION,
        "agents": index_agents,
        "packs": index_packs,
    }
    pub = REGISTRY / "publishers" / f"{PUBLISHER}.json"
    files[pub] = read_json(pub) or {
        "github_handle": PUBLISHER,
        "public_key": None,
        "created_at": "2026-10-06T00:00:00Z",
    }
    return files


def main() -> int:
    check = "--check" in sys.argv[1:]
    pack_dirs = sorted(p for p in PACKS_ROOT.iterdir() if (p / ".nandi" / "manifest.yaml").is_file())
    packs = [p for p in (load_pack(d) for d in pack_dirs) if p]
    # Prioritize new high-impact packs at top
    priority = {
        "finance-pack": 0,
        "trading-pack": 1,
        "healthcare-pack": 2,
        "restaurant-pack": 3,
        "local-marketing-pack": 4,
        "legal-pack": 5,
        "sales-pack": 6,
        "devops-pack": 7,
    }
    packs.sort(key=lambda p: (priority.get(p["id"], 8), p["id"]))

    # IDs must be unique across every pack (a user may install them all)
    seen: dict[str, str] = {}
    for pack in packs:
        for kind, ids in (("agent", [a["id"] for a in pack["agents"]]), ("workflow", pack["workflows"])):
            for i in ids:
                key = f"{kind}:{i}"
                if key in seen:
                    err(f"{kind} ID '{i}' is used by both {seen[key]} and {pack['id']}")
                seen[key] = pack["id"]

    files = build(packs)
    stale = []
    for path, data in files.items():
        current = read_json(path)
        if current != data:
            stale.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    known = set(files)
    for sub in ("agents", "packs"):
        for p in (REGISTRY / sub).glob("*.json") if (REGISTRY / sub).is_dir() else []:
            if p not in known:
                err(f"registry/{sub}/{p.name} has no matching pack content")

    n_agents = sum(len(p["agents"]) for p in packs)
    print(f"packs: {len(packs)}, agents: {n_agents}, workflows: {sum(len(p['workflows']) for p in packs)}")
    for p in packs:
        words = ", ".join(f"{a['id']} {a['words']}w" for a in p["agents"])
        print(f"  {p['id']}: {p['size_kb']} KB; {words}")
    if check and stale:
        for p in stale:
            err(f"{p.relative_to(REGISTRY)} is out of date: run tools/build_index.py")
    elif stale:
        print(f"updated {len(stale)} registry file(s)")
    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
