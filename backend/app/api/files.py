"""Serves locally stored files through short-lived signed links (development storage only)."""

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.errors import NotFound
from app.services.storage import LocalStorage, get_storage, verify_local_token

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{token}")
def download(token: str) -> Response:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFound()  # with S3 the browser downloads directly from presigned URLs
    payload = verify_local_token(token)
    data = storage.get(payload["k"])
    return Response(
        content=data,
        media_type=payload["c"],
        headers={
            "Content-Disposition": f'attachment; filename="{payload["f"]}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
