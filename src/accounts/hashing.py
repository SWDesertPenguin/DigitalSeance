# SPDX-License-Identifier: AGPL-3.0-or-later

"""Argon2id password hashing wrapper for spec 023 (FR-003, SC-005, SC-007).

Wraps :mod:`argon2` (the ``argon2-cffi`` PyPI package, pinned in
``pyproject.toml`` per Constitution §6.3) so the rest of the codebase
never touches the third-party API directly. A future swap to a
different argon2id implementation is an internal-architecture refactor,
not an FR-021 boundary change.

Parameters are sourced once at construction time from the
``SACP_PASSWORD_ARGON2_*`` env vars; per-instance state is the
underlying :class:`argon2.PasswordHasher`. Each
:class:`PasswordHasher` instance is process-local; the typical caller
constructs a single hasher in the account-service factory and shares
it across requests.

See ``specs/023-user-accounts/research.md`` §1 (library choice) and
§8 (transparent re-hash on parameter change) for the design notes,
and ``specs/023-user-accounts/contracts/env-vars.md`` for the env-var
shape.
"""

from __future__ import annotations

import logging
import os

from argon2 import PasswordHasher as _Argon2PasswordHasher
from argon2 import exceptions as _argon2_exceptions

# Defaults match contracts/env-vars.md and OWASP 2024.
_DEFAULT_TIME_COST = 2
_DEFAULT_MEMORY_COST_KB = 19456
# Parallelism is hardcoded per FR-003 — single-thread on the orchestrator.
_FIXED_PARALLELISM = 1
# OWASP 2024 minimum floors for argon2id at parallelism=1. Below these
# we WARN at construction time even though the validator accepts the
# value syntactically. The validator's [1,10] / [7168, 1048576] ranges
# are the syntactic envelope; the warn-floors below are the
# defense-in-depth alert that an operator dialed the parameters down
# to a non-OWASP-recommended value.
_OWASP_FLOOR_TIME_COST = 2
_OWASP_FLOOR_MEMORY_COST_KB = 19456

log = logging.getLogger(__name__)


def _read_env_int(name: str, default: int) -> int:
    """Read an int env var, falling back to ``default`` on empty / unset.

    The validators in ``src/config/validators.py`` already enforce the
    [min, max] range at startup; this helper just trusts the validator
    and parses. ``ValueError`` here would mean the validator was
    bypassed (e.g. tests setting the env directly without re-running
    the validator) — re-raise so the misconfiguration is loud.
    """
    raw = os.environ.get(name, "")
    if raw == "":
        return default
    return int(raw)


class PasswordHasher:
    """Argon2id wrapper exposing :meth:`hash`, :meth:`verify`, :meth:`needs_rehash`.

    ``time_cost`` and ``memory_cost`` are sourced from
    ``SACP_PASSWORD_ARGON2_TIME_COST`` and
    ``SACP_PASSWORD_ARGON2_MEMORY_COST_KB`` at construction time;
    ``parallelism`` is hardcoded to ``1`` per FR-003. Instances are
    process-local and immutable after construction — to apply a
    parameter change, replace the hasher (the typical pattern is one
    factory call per process, with the env vars validated at startup).
    """

    def __init__(
        self,
        *,
        time_cost: int | None = None,
        memory_cost_kb: int | None = None,
    ) -> None:
        resolved_time = (
            time_cost
            if time_cost is not None
            else _read_env_int("SACP_PASSWORD_ARGON2_TIME_COST", _DEFAULT_TIME_COST)
        )
        resolved_memory = (
            memory_cost_kb
            if memory_cost_kb is not None
            else _read_env_int(
                "SACP_PASSWORD_ARGON2_MEMORY_COST_KB",
                _DEFAULT_MEMORY_COST_KB,
            )
        )
        self._time_cost = resolved_time
        self._memory_cost_kb = resolved_memory
        self._inner = _Argon2PasswordHasher(
            time_cost=resolved_time,
            memory_cost=resolved_memory,
            parallelism=_FIXED_PARALLELISM,
        )
        self._maybe_warn_below_owasp_floor(resolved_time, resolved_memory)

    @staticmethod
    def _maybe_warn_below_owasp_floor(time_cost: int, memory_cost_kb: int) -> None:
        if time_cost < _OWASP_FLOOR_TIME_COST or memory_cost_kb < _OWASP_FLOOR_MEMORY_COST_KB:
            log.warning(
                "argon2id parameters below OWASP 2024 floor: "
                "time_cost=%d (floor=%d), memory_cost_kb=%d (floor=%d). "
                "Production deployments should raise these values.",
                time_cost,
                _OWASP_FLOOR_TIME_COST,
                memory_cost_kb,
                _OWASP_FLOOR_MEMORY_COST_KB,
            )

    @property
    def time_cost(self) -> int:
        return self._time_cost

    @property
    def memory_cost_kb(self) -> int:
        return self._memory_cost_kb

    def hash(self, plaintext: str) -> str:
        """Hash ``plaintext`` and return the encoded argon2id string.

        The returned form embeds the parameters used at hash time, so
        :meth:`needs_rehash` can compare against the current hasher's
        parameters on each subsequent verify.
        """
        return self._inner.hash(plaintext)

    def verify(self, stored_hash: str, plaintext: str) -> bool:
        """Verify ``plaintext`` against ``stored_hash``.

        Returns ``True`` on match, ``False`` on mismatch. The underlying
        library raises :class:`argon2.exceptions.VerifyMismatchError`
        on a clean mismatch; we translate to ``False``. Other argon2
        errors (corrupt hash, invalid hash format) propagate so the
        caller can decide whether to treat them as the same generic
        ``invalid_credentials`` failure as a mismatch (SC-005 timing
        contract requires identical responses).
        """
        try:
            return self._inner.verify(stored_hash, plaintext)
        except _argon2_exceptions.VerifyMismatchError:
            return False

    def needs_rehash(self, stored_hash: str) -> bool:
        """Return True iff ``stored_hash`` was produced with stale parameters.

        Backed by :meth:`argon2.PasswordHasher.check_needs_rehash` —
        SC-007's transparent re-hash flow consults this on every
        successful login and re-hashes the submitted plaintext when
        the answer is True.
        """
        return self._inner.check_needs_rehash(stored_hash)
