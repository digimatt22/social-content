from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select

from .db import create_db_engine, init_db, session_factory, session_scope
from .db_models import PrincipalRecord
from .services.auth import create_principal, create_service_credential


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Marketing OS identities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    admin = subparsers.add_parser("create-admin")
    admin.add_argument("username")
    admin.add_argument("--display-name", default="")
    token = subparsers.add_parser("create-service-token")
    token.add_argument("username")
    token.add_argument("--scope", action="append", default=[])
    token.add_argument("--description", default="")
    args = parser.parse_args(argv)

    engine = create_db_engine()
    init_db(engine)
    factory = session_factory(engine)
    if args.command == "create-admin":
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
        with session_scope(factory) as session:
            create_principal(
                session,
                username=args.username,
                password=password,
                roles={"admin", "operator", "viewer"},
                display_name=args.display_name,
            )
        print(f"Created administrator {args.username}.")
        return 0

    with session_scope(factory) as session:
        principal = session.scalar(select(PrincipalRecord).where(PrincipalRecord.username == args.username.lower()))
        if principal is None:
            principal = PrincipalRecord(
                principal_type="service",
                username=args.username.lower(),
                display_name=args.username,
                password_hash="",
                roles_json='["service"]',
            )
            session.add(principal)
            session.flush()
        elif principal.principal_type != "service":
            raise SystemExit("Service tokens require a dedicated service principal; choose a service identity name.")
        raw, _ = create_service_credential(
            session,
            principal,
            scopes=set(args.scope or ["read"]),
            description=args.description,
        )
    print("Store this token now; it will not be shown again:")
    print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
