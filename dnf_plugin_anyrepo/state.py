# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the dnf-plugin-anyrepo project.

"""State file helpers for cached AnyRepo repositories."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_state(cache_path: str) -> Dict[str, Any]:
    path = os.path.join(cache_path, "state.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def save_state(cache_path: str, state: Dict[str, Any]) -> None:
    os.makedirs(cache_path, exist_ok=True)
    path = os.path.join(cache_path, "state.json")
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_path, path)
