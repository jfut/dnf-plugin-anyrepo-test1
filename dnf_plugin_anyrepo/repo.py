# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the dnf-plugin-anyrepo project.

"""Local repository cache and createrepo_c orchestration."""

import os
import shutil
import subprocess
from typing import Iterable, Mapping


class RepoError(RuntimeError):
    """Raised when the local RPM repository cannot be prepared."""


def packages_dir(cache_path: str) -> str:
    return os.path.join(cache_path, "packages")


def subrepo_cache_path(cache_path: str, subrepo: str) -> str:
    """Return the cache path for an auxiliary repository under the main cache."""

    return os.path.join(cache_path, subrepo)


def has_repodata(cache_path: str) -> bool:
    return os.path.isdir(os.path.join(cache_path, "repodata"))


def ensure_cache_dirs(cache_path: str) -> None:
    os.makedirs(packages_dir(cache_path), exist_ok=True)


def clean_packages(cache_path: str) -> None:
    pkg_dir = packages_dir(cache_path)
    if os.path.isdir(pkg_dir):
        shutil.rmtree(pkg_dir)
    os.makedirs(pkg_dir, exist_ok=True)


def replace_cache(source_path: str, cache_path: str) -> None:
    """Replace the active cache only after a staged repository is complete."""

    backup_path = f"{cache_path}.old"
    if os.path.isdir(backup_path):
        shutil.rmtree(backup_path)
    if os.path.isdir(cache_path):
        os.replace(cache_path, backup_path)
    try:
        os.replace(source_path, cache_path)
    except Exception:
        if os.path.isdir(backup_path) and not os.path.isdir(cache_path):
            os.replace(backup_path, cache_path)
        raise
    else:
        if os.path.isdir(backup_path):
            shutil.rmtree(backup_path)


def remove_cache(cache_path: str) -> None:
    if os.path.isdir(cache_path):
        shutil.rmtree(cache_path)


def desired_asset_changed(state: Mapping[str, object], release: Mapping[str, object], assets: Iterable[Mapping[str, object]]) -> bool:
    asset_list = list(assets)
    return (
        state.get("latest_release_id") != release.get("id")
        or state.get("latest_tag") != release.get("tag_name")
        or state.get("asset_ids") != [asset.get("id") for asset in asset_list]
        or state.get("asset_updated_at") != [asset.get("updated_at") for asset in asset_list]
        or not state.get("asset_names")
    )


def run_createrepo(cache_path: str) -> None:
    """Generate repodata so DNF can consume the local file:// repository."""

    binary = shutil.which("createrepo_c")
    if not binary:
        raise RepoError("createrepo_c command is required")
    subprocess.run([binary, "--update", cache_path], check=True)
