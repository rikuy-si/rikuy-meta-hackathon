"""Actor grants: who may ask the gateway for what.

A grant binds one actor token to a set of bridges and actions, optionally
with an expiry. Tools verify before they touch the queue; revocation is
instant because verification is a lookup.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .audit import AuditLog
from .config import now_utc

ALL_ACTIONS = frozenset({"list_cameras", "live_image", "download_history", "upload"})


class GrantDenied(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Grant:
    id: str
    actor: str
    token: str
    bridges: Optional[frozenset[str]]  # None = every enrolled bridge
    actions: frozenset[str]
    expires_at: Optional[datetime] = None
    revoked: bool = False

    def __repr__(self) -> str:  # tokens stay out of logs
        return (
            f"Grant(id={self.id!r}, actor={self.actor!r}, bridges={self.bridges}, "
            f"actions={sorted(self.actions)}, revoked={self.revoked})"
        )


@dataclass
class _Counters:
    n: int = 0


class GrantStore:
    def __init__(self, audit: AuditLog) -> None:
        self.audit = audit
        self.lock = threading.RLock()
        self.grants: dict[str, Grant] = {}
        self._by_token: dict[str, str] = {}
        self._c = _Counters()

    def issue(
        self,
        actor: str,
        bridges: Optional[Iterable[str]] = None,
        actions: Iterable[str] = ALL_ACTIONS,
        ttl_secs: Optional[int] = None,
        token: Optional[str] = None,
    ) -> Grant:
        with self.lock:
            self._c.n += 1
            g = Grant(
                id=f"grant-{self._c.n:04d}",
                actor=actor,
                token=token or f"rikuy-actor-{secrets.token_hex(12)}",
                bridges=frozenset(bridges) if bridges is not None else None,
                actions=frozenset(actions),
                expires_at=(now_utc() + timedelta(seconds=ttl_secs)) if ttl_secs else None,
            )
            self.grants[g.id] = g
            self._by_token[g.token] = g.id
        self.audit.record("grant_issued", grant=g.id, actor=actor, bridges=sorted(bridges) if bridges else None, actions=sorted(g.actions), ttl_secs=ttl_secs)
        return g

    def verify(self, token: str, bridge: str, action: str) -> Grant:
        with self.lock:
            gid = self._by_token.get(token)
            g = self.grants.get(gid) if gid else None
        if g is None:
            raise GrantDenied("unknown actor token")
        if g.revoked:
            raise GrantDenied("actor token was revoked")
        if g.expires_at is not None and g.expires_at <= now_utc():
            raise GrantDenied("actor token expired")
        if g.bridges is not None and bridge not in g.bridges:
            raise GrantDenied(f"grant does not cover bridge {bridge!r}")
        if action not in g.actions:
            raise GrantDenied(f"grant does not allow {action!r}")
        return g

    def revoke(self, *, grant_id: Optional[str] = None, token: Optional[str] = None) -> None:
        with self.lock:
            g = None
            if grant_id:
                g = self.grants.get(grant_id)
            elif token:
                gid = self._by_token.get(token)
                g = self.grants.get(gid) if gid else None
            if g:
                g.revoked = True
        if g:
            self.audit.record("grant_revoked", grant=g.id, actor=g.actor)

    def bootstrap(self, actor: str, token: str) -> Grant:
        """The default demo grant (settings.default_actor_token)."""
        return self.issue(actor=actor, token=token)
