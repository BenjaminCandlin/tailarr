"""Logging in and out, and the login setting."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session

from ..core.auth import (
    COOKIE,
    MIN_PASSWORD,
    SESSION_DAYS,
    LoginSettings,
    check_password,
    end_all_sessions,
    end_session,
    get_login,
    hash_password,
    new_session,
    save_login,
    valid_session,
)
from .deps import get_session

router = APIRouter()


class AuthStatusOut(BaseModel):
    login_enabled: bool
    logged_in: bool  # True when no login is needed
    username: str | None


def _status(request: Request, session: Session) -> AuthStatusOut:
    login = get_login(session)
    if not login.enabled:
        return AuthStatusOut(login_enabled=False, logged_in=True, username=None)
    ok = valid_session(session, request.cookies.get(COOKIE))
    return AuthStatusOut(login_enabled=True, logged_in=ok, username=login.username if ok else None)


@router.get("/api/auth/status", response_model=AuthStatusOut)
def auth_status(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> AuthStatusOut:
    return _status(request, session)


class LoginIn(BaseModel):
    username: str
    password: str


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.post("/api/auth/login", response_model=AuthStatusOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> AuthStatusOut:
    settings = get_login(session)
    if not settings.enabled:
        return _status(request, session)
    failures = request.app.state.failed_logins
    address = request.client.host if request.client else "unknown"
    wait = failures.locked_for(address)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many wrong passwords. Please wait {max(1, wait // 60)} minute(s) and "
            "try again.",
        )
    if not (
        body.username.strip().casefold() == settings.username.casefold()
        and check_password(body.password, settings.password_hash)
    ):
        failures.failed(address)
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    failures.succeeded(address)
    _set_cookie(response, request, new_session(session))
    return AuthStatusOut(login_enabled=True, logged_in=True, username=settings.username)


@router.post("/api/auth/logout", response_model=AuthStatusOut)
def logout(
    request: Request, response: Response, session: Annotated[Session, Depends(get_session)]
) -> AuthStatusOut:
    end_session(session, request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    login_on = get_login(session).enabled
    return AuthStatusOut(login_enabled=login_on, logged_in=not login_on, username=None)


class LoginSettingsOut(BaseModel):
    enabled: bool
    username: str


class LoginSettingsIn(BaseModel):
    enabled: bool
    username: str = ""
    password: str = ""  # empty: keep the current password


@router.get("/api/settings/login", response_model=LoginSettingsOut)
def read_login(session: Annotated[Session, Depends(get_session)]) -> LoginSettingsOut:
    login = get_login(session)
    return LoginSettingsOut(enabled=login.enabled, username=login.username)


@router.put("/api/settings/login", response_model=LoginSettingsOut)
def update_login(
    body: LoginSettingsIn,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> LoginSettingsOut:
    """Switch the login on or off, or change the username/password.

    While the login is on, only someone logged in gets here (the middleware checks).
    """
    saved = get_login(session)
    if not body.enabled:
        save_login(session, LoginSettings(enabled=False, username=saved.username))
        end_all_sessions(session)
        return LoginSettingsOut(enabled=False, username=saved.username)
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Choose a username.")
    password_hash = saved.password_hash
    if body.password:
        if len(body.password) < MIN_PASSWORD:
            raise HTTPException(
                status_code=400,
                detail=f"Choose a password of at least {MIN_PASSWORD} characters.",
            )
        password_hash = hash_password(body.password)
    if not password_hash:
        raise HTTPException(status_code=400, detail="Choose a password.")
    changed_password = password_hash != saved.password_hash
    save_login(session, LoginSettings(enabled=True, username=username, password_hash=password_hash))
    if changed_password or not saved.enabled:
        # Everyone else is logged out; this browser stays logged in.
        end_all_sessions(session)
        _set_cookie(response, request, new_session(session))
    return LoginSettingsOut(enabled=True, username=username)
