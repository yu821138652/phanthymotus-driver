"""Beijing exhibition knowledge MCP card for the Unitree G1 bundle."""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import tempfile
import threading
from pathlib import Path
from typing import Any


_ENTRY_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class _KnowledgeStore:
    def __init__(self, data_path: str, seed_path: str):
        self._data_path = Path(data_path)
        self._seed_path = Path(seed_path)
        self._lock = threading.RLock()

    @staticmethod
    def _validate_catalog(catalog: Any) -> None:
        if not isinstance(catalog, dict) or not isinstance(catalog.get("exhibits"), dict):
            raise ValueError("knowledge catalog must contain an exhibits object")
        for entry_id, entry in catalog["exhibits"].items():
            if not isinstance(entry_id, str) or not _ENTRY_ID.fullmatch(entry_id):
                raise ValueError(f"invalid entry ID: {entry_id!r}")
            if not isinstance(entry, dict):
                raise ValueError(f"entry {entry_id!r} must be an object")
            for field in ("title", "content"):
                if not isinstance(entry.get(field), str) or not entry[field].strip():
                    raise ValueError(f"entry {entry_id!r} requires non-empty {field}")
            aliases = entry.get("aliases", [])
            if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
                raise ValueError(f"entry {entry_id!r} aliases must be a string array")

    def _save_unlocked(self, catalog: dict[str, Any]) -> None:
        self._validate_catalog(catalog)
        catalog["updatedAt"] = _now()
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self._data_path.parent, delete=False) as handle:
            json.dump(catalog, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_path = Path(handle.name)
        temporary_path.replace(self._data_path)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self._data_path.is_file():
            if not self._seed_path.is_file():
                raise RuntimeError(f"knowledge seed file is unavailable: {self._seed_path}")
            seed = json.loads(self._seed_path.read_text(encoding="utf-8"))
            self._save_unlocked(seed)
        catalog = json.loads(self._data_path.read_text(encoding="utf-8"))
        self._validate_catalog(catalog)
        return catalog

    def list_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            catalog = self._load_unlocked()
            entries = [
                {
                    "id": entry_id,
                    "title": entry["title"],
                    "aliases": entry.get("aliases", []),
                    "poseId": entry.get("poseId", ""),
                    "order": entry.get("order"),
                }
                for entry_id, entry in catalog["exhibits"].items()
            ]
        return sorted(entries, key=lambda item: (item["order"] is None, item["order"], item["title"]))

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._load_unlocked()["exhibits"].get(entry_id)
            return None if entry is None else {"id": entry_id, **copy.deepcopy(entry)}

    def search(self, query: str) -> list[dict[str, Any]]:
        normalized = "".join(query.casefold().split())
        if not normalized:
            return self.list_entries()
        direct_matches, content_matches = [], []
        for summary in self.list_entries():
            entry = self.get_entry(summary["id"])
            assert entry is not None
            identifiers = [entry["id"], entry["title"], *entry.get("aliases", [])]
            if any(normalized in "".join(value.casefold().split()) for value in identifiers):
                direct_matches.append(summary)
            elif normalized in "".join(entry["content"].casefold().split()):
                content_matches.append(summary)
        return direct_matches or content_matches

    def upsert(self, args: dict[str, Any]) -> dict[str, Any]:
        entry_id = args.get("entry_id", "")
        title = args.get("title", "")
        content = args.get("content", "")
        aliases_json = args.get("aliases_json", "[]")
        pose_id = args.get("pose_id", "")
        order = args.get("order", 0)
        if not isinstance(entry_id, str) or not _ENTRY_ID.fullmatch(entry_id):
            raise ValueError("entry_id must contain only lowercase letters, digits, and hyphens")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip():
            raise ValueError("title and content cannot be empty")
        if not isinstance(aliases_json, str):
            raise ValueError("aliases_json must be a JSON string array")
        try:
            aliases = json.loads(aliases_json)
        except json.JSONDecodeError as exc:
            raise ValueError("aliases_json must be a JSON string array") from exc
        if not isinstance(aliases, list) or not all(isinstance(alias, str) and alias.strip() for alias in aliases):
            raise ValueError("aliases_json must be a JSON string array")
        if not isinstance(pose_id, str) or not isinstance(order, int):
            raise ValueError("pose_id must be a string and order must be an integer")

        with self._lock:
            catalog = self._load_unlocked()
            previous = catalog["exhibits"].get(entry_id, {})
            entry = {
                "title": title.strip(),
                "aliases": [alias.strip() for alias in aliases],
                "content": content.strip(),
            }
            if pose_id.strip():
                entry["poseId"] = pose_id.strip()
            elif previous.get("poseId"):
                entry["poseId"] = previous["poseId"]
            if order > 0:
                entry["order"] = order
            elif previous.get("order") is not None:
                entry["order"] = previous["order"]
            catalog["exhibits"][entry_id] = entry
            self._save_unlocked(catalog)
            return {"id": entry_id, **entry}

    def delete(self, entry_id: str) -> dict[str, Any] | None:
        if not isinstance(entry_id, str) or not _ENTRY_ID.fullmatch(entry_id):
            raise ValueError("entry_id must contain only lowercase letters, digits, and hyphens")
        with self._lock:
            catalog = self._load_unlocked()
            removed = catalog["exhibits"].pop(entry_id, None)
            if removed is None:
                return None
            self._save_unlocked(catalog)
            return {"id": entry_id, **removed}

    def validate(self) -> dict[str, Any]:
        with self._lock:
            catalog = self._load_unlocked()
            pose_to_ids: dict[str, list[str]] = {}
            for entry_id, entry in catalog["exhibits"].items():
                pose_id = entry.get("poseId", "")
                if pose_id:
                    pose_to_ids.setdefault(pose_id, []).append(entry_id)
            duplicates = {pose_id: ids for pose_id, ids in pose_to_ids.items() if len(ids) > 1}
            return {
                "valid": not duplicates,
                "entryCount": len(catalog["exhibits"]),
                "duplicatePoseIds": duplicates,
                "updatedAt": catalog.get("updatedAt", ""),
            }


class ExhibitionKnowledgePlugin:
    """A non-motion G1 card that serves the Beijing exhibition knowledge base."""

    PREFIX = "exhibition_knowledge"

    def __init__(self, plugin_config: dict, namespace: str, executor):
        self._store = _KnowledgeStore(
            plugin_config.get("data_path", "/opt/phanthy-motus/data/exhibition-knowledge/beijing-exhibition.json"),
            plugin_config.get("seed_path", "/work/resource/knowledge/beijing-exhibition.json"),
        )

    def get_tool(self) -> dict:
        return {
            "name": self.PREFIX,
            "type": "actuator",
            "multiInstance": False,
            "description": "Beijing exhibition knowledge base. Read, search, validate, explicitly update, and explicitly delete exhibition narration and navigation metadata.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "get", "search", "upsert", "delete", "validate"]},
                    "entry_id": {"type": "string", "description": "Knowledge entry ID, for example token-factory or company."},
                    "query": {"type": "string", "description": "Exhibition name, alias, pose ID, or keyword."},
                    "title": {"type": "string", "description": "Display title for an upsert."},
                    "content": {"type": "string", "description": "Complete replacement narration text for an upsert."},
                    "aliases_json": {"type": "string", "description": "JSON string array of aliases, for example [\"Token Factory\", \"token factory\"]."},
                    "pose_id": {"type": "string", "description": "Optional navigation tag ID; empty preserves the existing value."},
                    "order": {"type": "integer", "description": "Optional positive tour order; zero preserves the existing value."},
                },
                "required": ["action"],
                "x-action-params": {
                    "list": {"params": [], "description": "List entry IDs, titles, aliases, pose IDs, and tour order."},
                    "get": {"params": ["entry_id"], "description": "Read one complete entry."},
                    "search": {"params": ["query"], "description": "Search by ID, title, alias, pose ID, or content keyword."},
                    "upsert": {"params": ["entry_id", "title", "content", "aliases_json", "pose_id", "order"], "description": "Create or fully replace one entry. Requires explicit user-approved content."},
                    "delete": {"params": ["entry_id"], "description": "Delete one entry by ID. Requires an explicit user request and prior lookup confirmation."},
                    "validate": {"params": [], "description": "Validate the knowledge base and report duplicate pose IDs."},
                },
            },
        }

    def start(self) -> None:
        self._store.validate()

    def stop(self) -> None:
        pass

    def dispatch(self, action: str, args: dict) -> dict | None:
        if action == "start":
            return {"state": "ready", "catalog": self._store.validate()}
        if action == "stop":
            return {"state": "idle"}
        if action == "info":
            return {"state": "running", "catalog": self._store.validate()}
        if action == "list":
            return {"entries": self._store.list_entries()}
        if action == "get":
            entry_id = args.get("entry_id", "")
            entry = self._store.get_entry(entry_id) if isinstance(entry_id, str) else None
            return entry or {"error": "entry_not_found", "entryId": entry_id}
        if action == "search":
            query = args.get("query", "")
            if not isinstance(query, str):
                return {"error": "validation_error", "message": "query must be a string"}
            return {"entries": self._store.search(query)}
        if action == "upsert":
            try:
                entry = self._store.upsert(args)
            except ValueError as exc:
                return {"error": "validation_error", "message": str(exc)}
            return {"status": "updated", "entry": entry, "catalog": self._store.validate()}
        if action == "delete":
            entry_id = args.get("entry_id", "")
            try:
                entry = self._store.delete(entry_id)
            except ValueError as exc:
                return {"error": "validation_error", "message": str(exc)}
            if entry is None:
                return {"error": "entry_not_found", "entryId": entry_id}
            return {"status": "deleted", "entry": entry, "catalog": self._store.validate()}
        if action == "validate":
            return self._store.validate()
        return None
