"""Tests for build_index.py's connector entries.

Run from the registry repo: python -m unittest discover tools

Each test copies the registry (and the pack folders next to it) into a temp
folder, adds one connector entry and runs the build there.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import build_index

REGISTRY = build_index.ROOT
SPEC_DIRS = [REGISTRY.parent / name / "registry-schema" for name in ("nandi-spec", "nandi-spec-wt-connectors")]

VALID = {
    "id": "fetch",
    "name": "Fetch",
    "description": "Reads a web page and returns it as Markdown.",
    "publisher": "vaultdbai",
    "repo": "github.com/vaultdbai/nandi-connectors",
    "path": "connectors/fetch",
    "latest_version": "1.0.0",
    "ref": "fetch-v1.0.0",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "signature": "ed25519:AAAA",
    "min_nandi_version": "0.1.0",
    "tags": ["web"],
    "kind": "mcp-stdio",
    "run": {"command": "uvx", "package": "mcp-server-fetch", "version": "2025.4.7"},
    "placement": "container",
    "auth": {"type": "none"},
    "tools": [{"name": "fetch", "description": "Fetch one URL.", "access": "read"}],
    "data": {"read": ["Public web pages you name"], "write": []},
    "hosts": ["*.example.com"],
    "icon_url": "https://example.com/icon.svg",
}


class ConnectorEntries(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "nandi-registry"
        ignore = shutil.ignore_patterns(".git", "__pycache__")
        shutil.copytree(REGISTRY, self.root, ignore=ignore)
        for pack in REGISTRY.parent.iterdir():
            if (pack / ".nandi" / "manifest.yaml").is_file():
                shutil.copytree(pack, self.tmp / pack.name, ignore=ignore)
        code, out = self.run_build("--check")
        if code != 0:
            self.skipTest(f"the registry copy doesn't pass on its own (are the packs next to it?):\n{out}")

    def run_build(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = build_index.main(list(argv), root=self.root)
        return code, out.getvalue()

    def add(self, entry: dict, name: str | None = None) -> None:
        folder = self.root / "connectors"
        folder.mkdir(exist_ok=True)
        with (folder / f"{name or entry['id']}.json").open("w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(entry, indent=2) + "\n")

    def assert_fails(self, entry: dict, message: str, name: str | None = None) -> None:
        self.add(entry, name)
        code, out = self.run_build("--check")
        self.assertEqual(code, 1, out)
        self.assertIn(message, out)

    def test_valid_stdio_entry_is_listed(self) -> None:
        self.add(VALID)
        code, out = self.run_build("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("index.json is out of date", out)

        code, out = self.run_build()
        self.assertEqual(code, 0, out)
        self.assertIn("connectors: 1", out)
        index = json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        listed = {k: v for k, v in VALID.items() if k != "icon_url"}
        self.assertEqual(index["connectors"], [listed])
        # The entry file is the publisher's: never rewritten
        entry = json.loads((self.root / "connectors" / "fetch.json").read_text(encoding="utf-8"))
        self.assertEqual(entry, VALID)

        code, out = self.run_build("--check")
        self.assertEqual(code, 0, out)

    def test_index_keeps_its_line_ending(self) -> None:
        index = self.root / "index.json"
        crlf = b"\r\n" in index.read_bytes()
        self.add(VALID)
        self.run_build()
        self.assertEqual(b"\r\n" in index.read_bytes(), crlf)
        self.assertNotIn(b"\r\n", (self.root / "connectors" / "fetch.json").read_bytes())

    def test_write_json_keeps_crlf_and_writes_lf_for_new_files(self) -> None:
        old, new = self.tmp / "old.json", self.tmp / "new.json"
        old.write_bytes(b'{\r\n  "a": 1\r\n}\r\n')
        build_index.write_json(old, {"a": 2})
        build_index.write_json(new, {"a": 2})
        self.assertEqual(old.read_bytes(), b'{\r\n  "a": 2\r\n}\r\n')
        self.assertEqual(new.read_bytes(), b'{\n  "a": 2\n}\n')

    def test_host_placement_fails(self) -> None:
        entry = {**VALID, "placement": "host"}
        self.assert_fails(entry, "connectors/fetch.json: " + build_index.HOST_PLACEMENT)
        self.assertIn("runs on the host: the public registry lists container connectors only", build_index.HOST_PLACEMENT)

    def test_version_ranges_fail(self) -> None:
        for version in ("^1.2.0", "~1.2.0", ">=1.0.0", "1.2.x", "*", "latest", "next"):
            with self.subTest(version=version):
                entry = copy.deepcopy(VALID)
                entry["run"]["version"] = version
                self.assert_fails(entry, "run.version")

    def test_http_entry_with_image_fails(self) -> None:
        entry = {**VALID, "kind": "mcp-http", "run": {"url": "https://mcp.example.com/mcp"}, "image": "ghcr.io/x/y:1"}
        self.assert_fails(entry, "an mcp-http connector has no image")

    def test_http_entry_without_image_passes(self) -> None:
        self.add({**VALID, "kind": "mcp-http", "run": {"url": "https://mcp.example.com/mcp"}})
        code, out = self.run_build()
        self.assertEqual(code, 0, out)

    def test_id_must_equal_file_name(self) -> None:
        self.assert_fails(VALID, "id 'fetch' must equal the file name", name="web-fetch")

    def test_other_bad_fields_fail(self) -> None:
        cases = {
            "unknown keys ['extra']": {"extra": 1},
            "kind must be one of": {"kind": "plugin"},
            "path must be relative": {"path": "../outside"},
            "commit must be the full 40-character SHA": {"commit": "abc123"},
            "signature must be 'ed25519:<base64>'": {"signature": "rsa:AAAA"},
            "tags must be a non-empty list": {"tags": []},
            "is not a lowercase host name": {"hosts": ["*"]},
            "publishers/nobody.json missing": {"publisher": "nobody"},
            "auth.type must be one of": {"auth": {"type": "password"}},
            "auth.env must list environment variable names": {"auth": {"type": "api_key", "env": ["api-key"]}},
            "tool name 'fetch' is listed twice": {"tools": VALID["tools"] * 2},
            "access must be read or write": {"tools": [{"name": "a", "description": "b", "access": "admin"}]},
            "data must be {read: [...], write: [...]}": {"data": {"read": []}},
            "latest_version 'v1' is not a semver version": {"latest_version": "v1"},
            "run.command must be npx or uvx": {"run": {**VALID["run"], "command": "node"}},
        }
        for message, change in cases.items():
            with self.subTest(message=message):
                self.assert_fails({**VALID, **change}, message)

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "jsonschema not installed")
    def test_entry_matches_the_spec_schema(self) -> None:
        spec = next((d for d in SPEC_DIRS if (d / "connector.schema.json").is_file()), None)
        if spec is None:
            self.skipTest("no nandi-spec checkout with connector.schema.json next to the registry")
        shutil.copytree(spec, self.tmp / "nandi-spec" / "registry-schema")
        self.add(VALID)
        code, out = self.run_build()
        self.assertEqual(code, 0, out)
        self.assertNotIn("schema:", out)

        self.add({**VALID, "placement": "host", "kind": "mcp-http", "run": {"url": "https://a.example.com"}})
        code, out = self.run_build("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("connectors/fetch.json: schema: placement", out)


if __name__ == "__main__":
    unittest.main()
