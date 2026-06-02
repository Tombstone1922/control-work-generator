import sys

from sqlalchemy import select

from app import models
from app.database import SessionLocal, init_db


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python promote_admin.py user@example.com")
        raise SystemExit(1)

    email = sys.argv[1].strip().lower()
    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(models.User).where(models.User.email == email))
        if user is None:
            print(f"User not found: {email}")
            raise SystemExit(2)
        user.role = "admin"
        user.is_active = True
        db.commit()
        print(f"Admin role granted: {email}")


if __name__ == "__main__":
    main()
