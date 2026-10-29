from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import HTTPException

Role = Literal["admin", "viewer"]


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    role: Role


class JWTAuthenticator:
    def __init__(self, secret: str, algorithm: str = "HS256") -> None:
        if len(secret) < 16:
            raise ValueError("JWT secret must be at least 16 characters")
        self.secret = secret
        self.algorithm = algorithm

    @classmethod
    def from_env(cls) -> "JWTAuthenticator":
        return cls(os.getenv("JWT_SECRET", "dev-only-change-me-please"))

    def authenticate_header(self, authorization: str | None) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(status_code=401, detail="Missing bearer token")
        try:
            claims = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"require": ["sub", "role", "exp"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid bearer token") from exc

        role = claims.get("role")
        if role not in {"admin", "viewer"}:
            raise HTTPException(status_code=403, detail="Unsupported role")
        return Principal(subject=str(claims["sub"]), role=role)


def issue_demo_token(subject: str, role: Role, secret: str, ttl_seconds: int = 3600) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": subject, "role": role, "iat": now, "exp": now + ttl_seconds},
        secret,
        algorithm="HS256",
    )
