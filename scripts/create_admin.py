"""Create (or reset the password of) an admin account:  python scripts/create_admin.py admin@example.com"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.db import session_scope  # noqa: E402
from app.core.security import hash_password, validate_password_strength  # noqa: E402
from app.models.user import AdminUser  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: create_admin.py EMAIL [ROLE=superadmin|admin|support]")
    email, role = sys.argv[1].lower(), (sys.argv[2] if len(sys.argv) > 2 else "superadmin")
    pw = getpass.getpass("Password (min 10 chars): ")
    if pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords differ")
    problems = validate_password_strength(pw)
    if problems:
        sys.exit(problems[0])
    with session_scope() as db:
        admin = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
        if admin is None:
            db.add(AdminUser(email=email, password_hash=hash_password(pw), role=role, is_active=True))
            print("Admin created:", email)
        else:
            admin.password_hash, admin.is_active = hash_password(pw), True
            print("Admin password updated:", email)


if __name__ == "__main__":
    main()
