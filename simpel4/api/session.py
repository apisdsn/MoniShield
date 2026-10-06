"""Masuk, keluar, dan akun sendiri (TRD §5.6, §8.2)."""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from .common import COOKIE, ApiError, _check_csrf, client_ip, public, require_user

router = APIRouter(prefix='/api')


class Login(BaseModel):
    username: str = ''
    password: str = ''


class ChangePassword(BaseModel):
    old_password: str = ''
    new_password: str = ''


def _me(user): return {k: user[k] for k in ('username', 'display_name', 'role', 'must_change_password')}


@router.post('/auth/login', dependencies=[Depends(public)])
def login(body: Login, request: Request, response: Response):
    _check_csrf(request)
    cfg, auth = request.app.state.cfg, request.app.state.auth
    token, user = auth.login(body.username, body.password, client_ip(request), request.headers.get('user-agent'))
    response.set_cookie(COOKIE, token, max_age=cfg.session_max_hours * 3600, httponly=True, secure=cfg.cookie_secure, samesite='strict', path='/')
    return _me(user)


@router.post('/auth/logout')
def logout(request: Request, response: Response, user=Depends(require_user)):
    request.app.state.auth.logout(request.cookies.get(COOKIE), user, client_ip(request))
    response.delete_cookie(COOKIE, path='/')
    return dict(ok=True)


@router.get('/me')
def me(user=Depends(require_user)): return _me(user)


@router.post('/me/password')
def change_password(body: ChangePassword, request: Request, user=Depends(require_user)):
    """Ganti sandi sendiri (butuh sandi sekarang); sesi lain milik user ini dicabut."""
    request.app.state.auth.change_password(user, body.old_password, body.new_password, keep_token=request.cookies.get(COOKIE), ip=client_ip(request))
    return dict(ok=True)
