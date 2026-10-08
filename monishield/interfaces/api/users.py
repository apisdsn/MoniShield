"""User management and audit log: admin only (TRD §5.6, §8.3)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from .common import client_ip, require_admin

router = APIRouter(prefix='/api/admin', dependencies=[Depends(require_admin)])


class NewUser(BaseModel):
    username: str = ''
    display_name: str = ''
    role: str = 'user'
    password: str = ''


class EditUser(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None


@router.get('/users')
def list_users(request: Request): return dict(users=request.app.state.auth.list_users())


@router.post('/users', status_code=201)
def create_user(body: NewUser, request: Request, admin=Depends(require_admin)):
    return request.app.state.auth.create_user(body.username, body.display_name, body.role, body.password, by=admin, ip=client_ip(request))


@router.patch('/users/{user_id}')
def edit_user(user_id: int, body: EditUser, request: Request, admin=Depends(require_admin)):
    return request.app.state.auth.update_user(user_id, admin, client_ip(request), body.display_name, body.role, body.active)


@router.post('/users/{user_id}/reset-password')
def reset_password(user_id: int, request: Request, admin=Depends(require_admin)):
    """The temporary password is shown ONCE in this response; it is not stored and not logged."""
    return dict(temporary_password=request.app.state.auth.reset_password(user_id, admin, client_ip(request)))


@router.delete('/users/{user_id}')
def delete_user(user_id: int, request: Request, admin=Depends(require_admin)):
    request.app.state.auth.delete_user(user_id, admin, client_ip(request))
    return dict(ok=True)


@router.get('/audit')
def audit(request: Request, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    total, rows = request.app.state.auth.audit_list(limit, offset)
    return dict(total=total, limit=limit, offset=offset, rows=rows)
