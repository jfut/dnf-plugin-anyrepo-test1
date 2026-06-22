# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the dnf-plugin-anyrepo project.

from setuptools import find_packages, setup


setup(
    name="dnf-plugin-anyrepo",
    version="0.1.0",
    description="DNF plugin that turns remote RPM assets into local file repositories",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "dnf-anyrepo=dnf_plugin_anyrepo.cli:main",
        ],
    },
)
