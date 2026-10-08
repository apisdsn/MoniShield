"""Sign in, sign out, and own account (TRD §5.6, §8.2)."""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from .common import COOKIE, ApiError, _check_csrf, client_ip, public, require_user

router = APIRouter(prefix='/api')


class Login(BaseModel):
    username: str = ''
    password: str = ''


class Forgot(BaseModel):
    login: str = ''   # username or email
    lang: str = 'id'  # language of the email (the sign-in page language)


class ChangePassword(BaseModel):
    old_password: str = ''
    new_password: str = ''


def _me(user): return {k: user.get(k) for k in ('username', 'display_name', 'email', 'role', 'must_change_password')}


@router.post('/auth/login', dependencies=[Depends(public)])
def login(body: Login, request: Request, response: Response):
    _check_csrf(request)
    cfg, auth = request.app.state.cfg, request.app.state.auth
    token, user = auth.login(body.username, body.password, client_ip(request), request.headers.get('user-agent'))
    response.set_cookie(COOKIE, token, max_age=cfg.session_max_hours * 3600, httponly=True, secure=cfg.cookie_secure, samesite='strict', path='/')
    return dict(_me(user), session_idle_minutes=auth.idle)


@router.get('/auth/options', dependencies=[Depends(public)])
def options(request: Request):
    """What the sign-in page may offer: "forgot password" only when the mail server is set up."""
    return dict(forgot_password=request.app.state.resets.available())


@router.post('/auth/forgot', dependencies=[Depends(public)])
def forgot(body: Forgot, request: Request):
    """Email a temporary password. The same answer whether or not the account exists (monishield/application/password_service.py)."""
    _check_csrf(request)
    return request.app.state.resets.forgot(body.login[:254], client_ip(request), body.lang)


@router.post('/auth/logout')
def logout(request: Request, response: Response, user=Depends(require_user)):
    request.app.state.auth.logout(request.cookies.get(COOKIE), user, client_ip(request))
    response.delete_cookie(COOKIE, path='/')
    return dict(ok=True)


@router.get('/me')
def me(request: Request, user=Depends(require_user)):
    # the idle limit is sent so the UI can warn 5 minutes before the session expires (DRD §6.9)
    return dict(_me(user), session_idle_minutes=request.app.state.auth.idle)


@router.post('/me/password')
def change_password(body: ChangePassword, request: Request, user=Depends(require_user)):
    """Change own password (needs the current password); this user's other sessions are revoked."""
    request.app.state.auth.change_password(user, body.old_password, body.new_password, keep_token=request.cookies.get(COOKIE), ip=client_ip(request))
    return dict(ok=True)
