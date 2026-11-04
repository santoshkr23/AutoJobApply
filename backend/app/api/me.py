"""Current user endpoints, including account deletion."""

from fastapi import APIRouter, Depends, Request, Response

from app.api.auth import clear_session_cookies, user_out
from app.core.audit import audit
from app.core.deps import DB, CurrentUser
from app.core.errors import AppError, Unauthorized
from app.core.ratelimit import rate_limit
from app.core.security import verify_password
from app.schemas.auth import DeleteAccountIn, MessageOut, UserOut
from app.services.accounts import delete_account

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
def get_me(db: DB, user: CurrentUser) -> UserOut:
    return user_out(db, user)


@router.delete("", response_model=MessageOut, dependencies=[Depends(rate_limit("delete_account", 3))])
def delete_me(body: DeleteAccountIn, request: Request, response: Response, db: DB, user: CurrentUser) -> MessageOut:
    if body.confirm != "DELETE":
        raise AppError('Type "DELETE" to confirm account deletion.', code="confirmation_required")
    if user.password_hash and not verify_password(body.password or "", user.password_hash):
        raise Unauthorized("Password is incorrect")
    audit(db, action="account.deleted", actor_type="user", actor_id=user.id, request=request)
    delete_account(db, user)
    db.commit()
    clear_session_cookies(response)
    return MessageOut(message="Your account and personal data have been deleted.")
