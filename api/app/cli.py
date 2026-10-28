"""Admin command line.

    python -m app.cli create-admin --email you@example.com --name "Kunle"
    python -m app.cli invite [--email friend@example.com] [--note "Ada"]
    python -m app.cli reset-link --email someone@example.com

Passwords are read interactively (or from WW_ADMIN_PASSWORD for automation);
they are never accepted as command-line arguments, which would leak into shell history.
"""

import argparse
import getpass
import os
import sys

from fastapi import HTTPException
from sqlalchemy import func, select

from app.audit.service import record as audit
from app.auth.service import create_invite, create_user, invite_url, issue_reset_token, reset_url
from app.db.models import User
from app.db.session import get_sessionmaker


def _password() -> str:
    env = os.environ.get("WW_ADMIN_PASSWORD")
    if env:
        return env
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wealthwise")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--name", required=True)
    i = sub.add_parser("invite")
    i.add_argument("--email")
    i.add_argument("--note")
    r = sub.add_parser("reset-link")
    r.add_argument("--email", required=True)
    sub.add_parser("categorise-pending", help="Seed categories and categorise new data")
    args = p.parse_args(argv)

    db = get_sessionmaker()()
    try:
        if args.cmd == "create-admin":
            user = create_user(
                db, email=args.email, password=_password(), display_name=args.name, role="admin"
            )
            audit(db, "cli.admin_created", user_id=user.id, details={"via": "cli"})
            db.commit()
            print(f"Admin account created for {user.email}.")
        elif args.cmd == "invite":
            admin_id = db.scalar(select(func.min(User.id)).where(User.role == "admin"))
            inv, token = create_invite(db, created_by=admin_id, email=args.email, note=args.note)
            audit(db, "cli.invite_created", target_type="invite", target_id=str(inv.public_id))
            db.commit()
            print(f"Invite link (valid until {inv.expires_at:%Y-%m-%d %H:%M} UTC):")
            print(invite_url(token))
        elif args.cmd == "reset-link":
            target = db.scalar(select(User).where(User.email == args.email))
            if target is None:
                sys.exit("No user with that email.")
            token = issue_reset_token(db, target)
            audit(db, "cli.reset_link_issued", user_id=target.id)
            db.commit()
            print("Password reset link (single use):")
            print(reset_url(token))
        elif args.cmd == "categorise-pending":
            from app.categorise.service import recategorise, seed_defaults

            total = 0
            for uid in db.scalars(select(User.id)):
                seed_defaults(db, uid)
                db.flush()
                total += recategorise(db, uid, only_sources=("none",))
            db.commit()
            print(f"Categorised {total} transaction(s).")
    except HTTPException as exc:
        db.rollback()
        sys.exit(f"Error: {exc.detail}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
