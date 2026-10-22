from getpass import getpass

from sqlalchemy import select

from database import SessionLocal
from models import AuditLog, User, UserRole
from security import hash_password


def main():
    email = input("Admin email: ").strip().lower()
    full_name = input("Admin full name: ").strip()
    password = getpass("Admin password (hidden): ")
    confirm_password = getpass("Confirm admin password: ")

    if not email or not full_name:
        print("Email and full name are required.")
        return

    if len(password) < 12:
        print("Use an admin password with at least 12 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    db = SessionLocal()

    try:
        existing_admin = db.scalar(
            select(User).where(User.role == UserRole.ADMIN).limit(1)
        )

        if existing_admin:
            print("An ADMIN account already exists. Bootstrap cancelled.")
            return

        existing_user = db.scalar(
            select(User).where(User.email == email)
        )

        if existing_user:
            print("This email already belongs to an account.")
            return

        admin = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )

        db.add(admin)
        db.flush()

        db.add(
            AuditLog(
                user_id=admin.id,
                action="ADMIN_BOOTSTRAPPED",
                entity_type="User",
                entity_id=admin.id,
                details="Initial administrator account created",
            )
        )

        db.commit()
        print(f"Admin account created successfully: {email}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
