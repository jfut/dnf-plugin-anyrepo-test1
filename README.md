# dnf-plugin-anyrepo

![Tag](https://img.shields.io/github/tag/jfut/dnf-plugin-anyrepo.svg)
[![License](https://img.shields.io/badge/license-Apache%202-blue)](https://github.com/jfut/dnf-plugin-anyrepo/blob/main/LICENSE)

`dnf-plugin-anyrepo` is a DNF plugin that turns configured remote RPM assets into local `file://` repositories for DNF.

The current implementation supports GitHub Releases via `source = github-release`.

## Why use it

With this plugin, users can install and update RPMs published as GitHub release assets through ordinary DNF commands instead of downloading RPM files manually.

Typical examples:

- `https://github.com/jfut/dnf-plugin-anyrepo/releases`
- `https://github.com/jfut/prec/releases`

Once configured, users can run commands such as:

```bash
dnf install prec
dnf update prec
```

Dependency resolution and package version selection are still handled by DNF itself.

## Installation

Install from GitHub Releases by choosing the RPM that matches the target RHEL major version:

```bash
# RHEL 8, AlmaLinux 8, Rocky Linux 8, and other compatible distributions.
dnf install https://github.com/jfut/dnf-plugin-anyrepo/releases/download/vX.Y.Z/dist/dnf-plugin-anyrepo-x.y.z-n.el8.noarch.rpm

# RHEL 9, AlmaLinux 9, Rocky Linux 9, and other compatible distributions.
dnf install https://github.com/jfut/dnf-plugin-anyrepo/releases/download/vX.Y.Z/dist/dnf-plugin-anyrepo-x.y.z-n.el9.noarch.rpm

# RHEL 10, AlmaLinux 10, Rocky Linux 10, and other compatible distributions.
dnf install https://github.com/jfut/dnf-plugin-anyrepo/releases/download/vX.Y.Z/dist/dnf-plugin-anyrepo-x.y.z-n.el10.noarch.rpm
```

## Example using prec

After installation, a typical workflow for [prec](https://github.com/jfut/prec) looks like this:

```bash
# Register the GitHub repository.
# dnf-anyrepo add https://github.com/jfut/prec --name prec
/etc/dnf/plugins/anyrepo.conf: Added [prec]

# Inspect the configured repository.
dnf-anyrepo list
dnf-anyrepo show prec

# Refresh the local cache explicitly.
dnf-anyrepo refresh prec

# Install and update the package through DNF.
dnf install prec
dnf update prec

# Remove the repository definition and cached RPMs when no longer needed.
dnf-anyrepo remove prec --purge-cache
/etc/dnf/plugins/anyrepo.conf: Removed [prec]
```

## DNF integration

The user-facing master switch is:

```text
/etc/yum.repos.d/anyrepo.repo
```

Installed content:

```ini
[anyrepo]
name = AnyRepo repositories
enabled = 1
baseurl = file:///var/empty
skip_if_unavailable = 1
gpgcheck = 0
```

Set `enabled = 0` in that file to disable all AnyRepo-managed repositories for DNF commands.

The `gpgcheck` value in that file is also inherited by the dynamic
`github.com:<owner>:<repo>` repositories created by the plugin:

- `gpgcheck = 0` keeps DNF signature checks disabled for AnyRepo packages
- `gpgcheck = 1` enables normal DNF signature checks for AnyRepo packages
- when `gpgcheck = 1`, unsigned RPMs are rejected by DNF instead of using the
  AnyRepo unsigned-package warning flow

When enabled, the plugin:

- disables the static `anyrepo` repo entry itself
- refreshes configured repositories as needed
- registers cached repositories as DNF `file://` repos
- clears AnyRepo caches during `dnf clean all`

## Configuration

The `dnf-plugin-anyrepo` RPM package installs:

- `/etc/dnf/plugins/anyrepo.conf`
- `/etc/yum.repos.d/anyrepo.repo`
- `dnf-anyrepo`
- the DNF plugin shim under `dnf-plugins/anyrepo.py`

Main config path:

```text
/etc/dnf/plugins/anyrepo.conf
```

Example:

```ini
[main]
cache_dir = /var/cache/dnf/anyrepo
refresh_interval = 600
minimum_release_age = 3d
debug = 0

[dnf-plugin-anyrepo]
source = github-release
url = https://github.com/jfut/dnf-plugin-anyrepo
asset_regex = .*\.rpm$
minimum_release_age = 1800

[prec]
source = github-release
url = https://github.com/jfut/prec
asset_regex = .*\.rpm$
```

Configuration values are resolved in this order:

```text
repo section
  -> [main]
  -> built-in defaults
```

Default values:

```text
cache_dir=/var/cache/dnf/anyrepo
refresh_interval=600
minimum_release_age=259200
debug=0
source=github-release
enabled=true
asset_regex=.*\.rpm$
```

## Repository settings

Per-repository sections support these keys:

- `source`
- `url`
- `asset_regex`
- `enabled`
- `minimum_release_age`
- `cache_dir`
- `refresh_interval`
- `arch`
- `releasever`
- `github_token_file`

Notes:

- `url` must be a GitHub repository URL
- `source` must currently be `github-release`
- `enabled = false` disables only that repository
- `github_token_file` is read and used as a GitHub API bearer token

## Asset selection

Asset selection happens in this order:

1. Match `asset_regex`
2. Match RPM architecture
3. Match RHEL release marker when applicable

Architecture behavior:

- If `arch` is unset, the current machine architecture is used
- `amd64` is normalized to `x86_64`
- `arm64` is normalized to `aarch64`
- `noarch` RPMs are always allowed together with the selected architecture

Release version behavior:

- If `releasever` is unset, the plugin tries to detect `el8`, `el9`, or `el10`
- When assets contain EL-specific variants such as `.el9.x86_64.rpm`, the plugin keeps the exact `releasever` when available
- If the exact EL variant is missing, the plugin falls back to the nearest lower major such as `el10 -> el9 -> el8`
- Assets without an EL marker remain eligible

## Refresh behavior

The plugin refreshes a repository when one of these is true:

- there is no cache yet
- cached `arch` differs from the current config
- cached `releasever` differs from the current config
- `repodata/` is missing
- `refresh_interval` has elapsed since the last refresh

`refresh_interval` and `minimum_release_age` accept either raw seconds or a duration suffix:

- `30m`
- `1h`
- `2d`

## minimum_release_age

`minimum_release_age` delays adoption of a newly published release.

The check uses GitHub `published_at`:

```text
now - published_at >= minimum_release_age
```

If the latest release is too new:

- existing cached metadata is kept when a usable cache already exists
- a new repository is not generated when no cache exists yet

This helps avoid immediately shipping a release while assets are still being uploaded or verified.

Examples:

```bash
# Set the global default release age to 1 day.
dnf-anyrepo config set minimum_release_age 1d

# Override only one repository to 30 minutes.
dnf-anyrepo set NAME minimum_release_age 30m
```

The first command updates `[main]` and affects repositories that inherit the
global setting.

The second command updates the named repository section and overrides the
global value only for that repository.

## How it works

`dnf-plugin-anyrepo` does not ask DNF to consume GitHub directly.

Instead, it mirrors matching RPM assets into a local cache and generates repository metadata there.

```text
GitHub Releases API
  -> select latest published release
  -> filter assets
  -> download RPM assets
  -> /var/cache/dnf/anyrepo/<name>
  -> createrepo_c
  -> local file:// repository
  -> DNF
```

The plugin's responsibility is limited to turning remote release assets into a normal local repository. Dependency solving remains DNF's job.

## Scope

- Current source: `github-release`
- Target environments: RHEL 8, RHEL 9, RHEL 10, and other compatible distributions
- Current GitHub URL requirement: `https://github.com/<owner>/<repo>`
- Draft and prerelease releases are ignored when the provider falls back to the releases list API

## CLI

Add repositories:

```bash
# basic
dnf-anyrepo add https://github.com/jfut/prec
dnf-anyrepo add https://github.com/jfut/sslcert-cli --name sslcert

# with options
dnf-anyrepo add https://github.com/jfut/prec --asset-regex '.*\.rpm$'
dnf-anyrepo add https://github.com/jfut/prec --minimum-release-age 30m
dnf-anyrepo add https://github.com/jfut/prec --arch x86_64 --releasever el9
dnf-anyrepo add https://github.com/jfut/prec --github-token-file /etc/anyrepo/github.token

# list
dnf-anyrepo list
```

Global configuration:

```bash
dnf-anyrepo config get minimum_release_age
dnf-anyrepo config set minimum_release_age 1h
dnf-anyrepo config unset minimum_release_age
/etc/dnf/plugins/anyrepo.conf: Unset [main] minimum_release_age
```

Update repository settings:

```bash
dnf-anyrepo show prec

dnf-anyrepo set prec minimum_release_age 30m
dnf-anyrepo set sslcert minimum_release_age 3d
dnf-anyrepo set prec enabled false
dnf-anyrepo unset prec minimum_release_age
/etc/dnf/plugins/anyrepo.conf: Unset [prec] minimum_release_age
```

Refresh and remove repositories:

```bash
dnf-anyrepo refresh
dnf-anyrepo refresh prec
dnf-anyrepo refresh prec --force

dnf-anyrepo remove prec --purge-cache
```

## Development

Common local tasks:

```bash
just lint
just test
just exec-test
just check
just snapshot
```

The codebase targets Python 3.6-compatible syntax.

## Release

1. Run `git tag -s vX.Y.Z -m vX.Y.Z`.
2. Run `git push origin vX.Y.Z` and wait for the Release to be created.
3. Edit the created Release.
4. Press the `Generate release notes` button and edit the release notes.
5. Press the `Update release` button.

## License

Apache-2.0
