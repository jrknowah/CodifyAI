"""
Admin bootstrap CLI. Public self-registration is disabled, so the first
administrator is created from the server shell:

    python -m app.cli create-admin --email admin@facility.com --name "Jane Admin"

The password is prompted for (never passed on the command line, where it would
land in shell history and the process list).
"""
import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError

from app.db.session import AsyncSessionLocal
from app.models.models import AuditLog, AuditAction, UserRole
from app.schemas.schemas import UserCreate


async def _create_admin(email: str, name: str, password: str) -> None:
    from app.services.user_service import create_user
    async with AsyncSessionLocal() as db:
        user = await create_user(
            db, UserCreate(email=email, password=password, full_name=name), role=UserRole.admin,
        )
        db.add(AuditLog(
            user_id=user.id, action=AuditAction.user_created, resource_id=str(user.id),
            ip_address="cli", user_agent="app.cli",
            detail={"email": user.email, "role": "admin", "source": "cli"},
        ))
        await db.commit()
        print(f"Created admin {user.email} ({user.id})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="Create an administrator account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match.")
    try:
        UserCreate(email=args.email, password=password, full_name=args.name)
    except ValidationError as e:
        sys.exit("; ".join(err["msg"] for err in e.errors()))
    asyncio.run(_create_admin(args.email, args.name, password))


if __name__ == "__main__":
    main()
