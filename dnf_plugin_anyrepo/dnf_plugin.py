# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the dnf-plugin-anyrepo project.

"""DNF plugin entry point.

This module is installed as a DNF plugin shim and registers cached AnyRepo
repositories as ordinary file:// repositories before dependency
resolution starts.
"""

import configparser
import os
import shutil
import sys

from dnf_plugin_anyrepo.config import (
    DEFAULT_CACHE_DIR,
    DEFAULT_CONFIG_PATH,
    ConfigError,
    load_config,
    parse_bool,
)
from dnf_plugin_anyrepo.manager import RepositoryManager
from dnf_plugin_anyrepo.repo import has_repodata


REPO_SWITCH_ID = "anyrepo"
REPO_SWITCH_PATH = "/etc/yum.repos.d/anyrepo.repo"
ORANGE = "\033[38;5;214m"
COLOR_RESET = "\033[0m"


def github_repo_id(repo):
    """Use a GitHub-derived id that libdnf accepts as a repository id."""

    owner, name = repo.owner_repo
    return f"github.com:{owner}:{name}"


def repo_switch_enabled(path=REPO_SWITCH_PATH):
    """Read the user-facing DNF repo switch for this plugin."""

    import configparser

    parser = configparser.ConfigParser()
    parser.read(path)
    if not parser.has_section(REPO_SWITCH_ID):
        return True
    return parse_bool(parser[REPO_SWITCH_ID].get("enabled", "1"))


def repo_switch_gpgcheck(path=REPO_SWITCH_PATH):
    """Read the user-facing gpgcheck setting for dynamic AnyRepo repositories."""

    import configparser

    parser = configparser.ConfigParser()
    parser.read(path)
    if not parser.has_section(REPO_SWITCH_ID):
        return False
    return parse_bool(parser[REPO_SWITCH_ID].get("gpgcheck", "0"))


def anyrepo_cache_dirs(config_path: str = DEFAULT_CONFIG_PATH):
    """Collect every configured AnyRepo cache root for clean-all integration."""

    directories = {DEFAULT_CACHE_DIR}
    try:
        config = load_config(config_path)
    except ConfigError:
        return sorted(directories)
    directories.add(config.main.cache_dir)
    directories.update(repo.cache_dir for repo in config.repos.values())
    return sorted(os.path.abspath(path) for path in directories if path)


def clear_anyrepo_cache_dirs(paths) -> int:
    """Remove cached AnyRepo files while keeping the cache root directory."""

    removed = 0
    for path in paths:
        if not os.path.isdir(path):
            continue
        normalized = os.path.abspath(path)
        if normalized == os.path.sep:
            continue
        for entry in os.listdir(normalized):
            target = os.path.join(normalized, entry)
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            else:
                os.unlink(target)
            removed += 1
    return removed


try:
    import dnf
except ImportError:  # pragma: no cover - exercised only inside DNF.
    dnf = None


if dnf is not None:
    import dnf.cli.commands.clean as dnf_clean
    import rpm
    from dnf.transaction import FORWARD_ACTIONS

    def _patch_clean_command():
        if getattr(dnf_clean.CleanCommand, "_anyrepo_clean_patched", False):
            return

        original_run = dnf_clean.CleanCommand.run

        def run_with_anyrepo(self):
            result = original_run(self)
            if "all" not in set(getattr(self.opts, "type", [])):
                return result
            removed = clear_anyrepo_cache_dirs(anyrepo_cache_dirs())
            print(f"AnyRepo cache files cleared: {removed}", file=sys.stderr)
            return result

        dnf_clean.CleanCommand.run = run_with_anyrepo
        dnf_clean.CleanCommand._anyrepo_clean_patched = True

    _patch_clean_command()

    class AnyRepoPlugin(dnf.Plugin):
        name = "anyrepo"

        def config(self):
            self._disable_repo_switch()
            try:
                manager = RepositoryManager()
            except (ConfigError, OSError, configparser.Error) as exc:
                self._anyrepo_debug = False
                self._anyrepo_repo_ids = set()
                self._warn(f"failed to load AnyRepo configuration: {exc}")
                return
            self._anyrepo_debug = manager.config.main.debug
            self._anyrepo_repo_ids = {github_repo_id(repo) for repo in manager.enabled_repos()}
            try:
                enabled = repo_switch_enabled()
                self._anyrepo_gpgcheck = repo_switch_gpgcheck()
            except ValueError as exc:
                self._warn(f"invalid anyrepo switch value, defaulting to enabled: {exc}")
                enabled = True
                self._anyrepo_gpgcheck = False
            if not enabled:
                self._debug("AnyRepo repositories are disabled by anyrepo")
                return

            for repo in manager.enabled_repos():
                try:
                    manager.refresh(repo.name, force=False)
                    self._debug(f"checked GitHub repository {repo.name}")
                except Exception as exc:
                    self._warn(f"failed to refresh GitHub repository {repo.name}: {exc}")
            for repo in manager.enabled_repos():
                if has_repodata(repo.cache_path):
                    self._add_file_repo(repo)

        def _add_file_repo(self, repo):
            repo_id = github_repo_id(repo)
            baseurl = "file://" + os.path.abspath(repo.cache_path)
            if getattr(self, "_anyrepo_debug", False):
                dnf_repo = self.base.repos.add_new_repo(repo_id, self.base.conf, baseurl=[baseurl])
            else:
                # Register the repository without DNF's informational "Added ..." log.
                dnf_repo = dnf.repo.Repo(repo_id, self.base.conf)
                dnf_repo.baseurl += [baseurl]
                self.base.repos.add(dnf_repo)
            dnf_repo.name = f"GitHub {repo.name}"
            dnf_repo.enabled = True
            dnf_repo.skip_if_unavailable = True
            dnf_repo.metadata_expire = 0
            dnf_repo.gpgcheck = getattr(self, "_anyrepo_gpgcheck", False)
            dnf_repo.repo_gpgcheck = False

        def resolved(self):
            packages = self._unsigned_anyrepo_packages()
            if not packages:
                return
            self._warn_unsigned_packages(packages)

        def _disable_repo_switch(self):
            if REPO_SWITCH_ID in self.base.repos:
                self.base.repos[REPO_SWITCH_ID].disable()

        def _debug(self, message):
            if not getattr(self, "_anyrepo_debug", False):
                return
            logger = getattr(self, "logger", None)
            if logger:
                logger.debug(message)
            else:
                print(message, file=sys.stderr)

        def _warn(self, message):
            logger = getattr(self, "logger", None)
            if logger:
                logger.warning(message)
            else:
                print(message, file=sys.stderr)

        def _unsigned_anyrepo_packages(self):
            packages = []
            transaction = getattr(self.base, "transaction", None) or []
            for item in transaction:
                if item.action not in FORWARD_ACTIONS:
                    continue
                pkg = item.pkg
                if pkg.repoid not in getattr(self, "_anyrepo_repo_ids", set()):
                    continue
                if self._package_is_signed(pkg):
                    continue
                packages.append(pkg)
            return packages

        def _package_is_signed(self, pkg):
            path = pkg.localPkg()
            ts = rpm.TransactionSet()
            ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
            with open(path, "rb") as fh:
                header = ts.hdrFromFdno(fh)
            signature_tags = (
                rpm.RPMTAG_RSAHEADER,
                rpm.RPMTAG_DSAHEADER,
                rpm.RPMTAG_SIGPGP,
                rpm.RPMTAG_SIGGPG,
                rpm.RPMTAG_OPENPGP,
            )
            for tag in signature_tags:
                value = header[tag]
                if value:
                    return True
            return False

        def _warn_unsigned_packages(self, packages):
            names = sorted(pkg.name for pkg in packages)
            lines = ["", "WARNING: Continue installing unsigned AnyRepo packages?"]
            lines.extend(f"- {name}" for name in names)
            if self.base.conf.assumeyes:
                lines.append("Proceeding because -y was specified.")
            lines.append("")
            self._print_unsigned_warning_block(lines)

        def _print_unsigned_warning_block(self, lines):
            text = "\n".join(lines)
            if sys.stderr.isatty():
                text = f"{ORANGE}{text}{COLOR_RESET}"
            print(text, file=sys.stderr)
