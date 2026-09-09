from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from reweft.domain.models import Role
from reweft.persistence import Database


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    workspace_id: UUID
    role: Role
    scopes: frozenset[str]


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: frozenset({"workspace:admin", "source:admin", "inference:admin", "assessment:run", "evidence:write", "evidence:read", "lineage:write", "lineage:read", "export"}),
    Role.ADMINISTRATOR: frozenset({"source:admin", "inference:admin", "assessment:run", "evidence:write", "evidence:read", "lineage:write", "lineage:read", "export"}),
    Role.OPERATOR: frozenset({"assessment:run", "evidence:write", "evidence:read", "lineage:write", "lineage:read", "export"}),
    Role.CONTRIBUTOR: frozenset({"evidence:read", "lineage:read"}),
    Role.VIEWER: frozenset({"evidence:read", "lineage:read"}),
}


class AuthenticationError(ValueError):
    pass


class AuthorizationError(ValueError):
    pass


class AuthService:
    def __init__(self, database: Database):
        self.database = database

    def install_bootstrap_token(self, token: str, *, lifetime_minutes: int = 15) -> None:
        if len(token) < 32:
            raise ValueError("bootstrap token must contain at least 32 characters")
        now = _now()
        with self.database.transaction(immediate=True) as connection:
            # Do not create new bootstrap authority after the first user exists.
            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return
            connection.execute(
                "INSERT OR IGNORE INTO bootstrap_tokens(token_hash,expires_at) VALUES(?,?)",
                (_hash(token), (now + timedelta(minutes=lifetime_minutes)).isoformat()),
            )

    def bootstrap(self, *, token: str, email: str, display_name: str, workspace_name: str) -> tuple[UUID, UUID, str]:
        now = _now()
        user_id, workspace_id = uuid4(), uuid4()
        api_token = secrets.token_urlsafe(40)
        try:
            with self.database.transaction(immediate=True) as connection:
                record = connection.execute("SELECT * FROM bootstrap_tokens WHERE token_hash=?", (_hash(token),)).fetchone()
                if not record or record["consumed_at"] or datetime.fromisoformat(record["expires_at"]) <= now:
                    raise AuthenticationError("invalid, expired, or consumed bootstrap token")
                if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise AuthenticationError("installation is already bootstrapped")
                connection.execute("INSERT INTO users(id,email,display_name,created_at) VALUES(?,?,?,?)", (str(user_id), email.casefold(), display_name, now.isoformat()))
                connection.execute("INSERT INTO workspaces(id,name,created_at) VALUES(?,?,?)", (str(workspace_id), workspace_name, now.isoformat()))
                connection.execute("INSERT INTO memberships(workspace_id,user_id,role) VALUES(?,?,?)", (str(workspace_id), str(user_id), Role.OWNER.value))
                connection.execute(
                    "INSERT INTO api_tokens(id,user_id,token_hash,scopes_json,created_at) VALUES(?,?,?,?,?)",
                    (str(uuid4()), str(user_id), _hash(api_token), "[]", now.isoformat()),
                )
                connection.execute("UPDATE bootstrap_tokens SET consumed_at=? WHERE token_hash=?", (now.isoformat(), _hash(token)))
        except sqlite3.IntegrityError as exc:
            raise AuthenticationError("bootstrap identity conflicts with existing state") from exc
        return user_id, workspace_id, api_token

    def authenticate(self, bearer_token: str, workspace_id: UUID) -> AuthContext:
        with self.database.connect() as connection:
            record = connection.execute(
                "SELECT t.user_id,t.scopes_json,t.expires_at,t.revoked_at,m.role FROM api_tokens t JOIN memberships m ON m.user_id=t.user_id WHERE t.token_hash=? AND m.workspace_id=?",
                (_hash(bearer_token), str(workspace_id)),
            ).fetchone()
        if not record or record["revoked_at"]:
            raise AuthenticationError("invalid token or workspace")
        if record["expires_at"] and datetime.fromisoformat(record["expires_at"]) <= _now():
            raise AuthenticationError("token has expired")
        import json

        explicit = frozenset(json.loads(record["scopes_json"]))
        role = Role(record["role"])
        scopes = ROLE_PERMISSIONS[role] if not explicit else ROLE_PERMISSIONS[role] & explicit
        return AuthContext(UUID(record["user_id"]), workspace_id, role, scopes)

    @staticmethod
    def require(context: AuthContext, permission: str) -> None:
        if permission not in context.scopes:
            raise AuthorizationError(f"permission required: {permission}")


def generate_bootstrap_token() -> str:
    return secrets.token_urlsafe(32)

