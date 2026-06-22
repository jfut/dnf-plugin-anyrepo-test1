# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the dnf-plugin-anyrepo project.

"""Provider protocol used by repository refresh code."""

from typing import Mapping, Sequence


class Provider:
    def refresh(self) -> bool:
        raise NotImplementedError

    def list_assets(self) -> Sequence[Mapping[str, object]]:
        raise NotImplementedError

    def download(self) -> None:
        raise NotImplementedError
