"""memoir-cli: the commands the images run.

memoir-cli serve      migrate, then serve the API on :8000
memoir-cli worker     run the job worker until stopped
memoir-cli migrate    apply the database migrations
memoir-cli openapi    print the OpenAPI document (the web client is built from it)
"""

import argparse
import getpass
import importlib
import json
import signal
import sys
import threading

from app.core.logging import configure
from app.core.settings import get_settings


def _migrate() -> None:
    from app.core.db import get_engine
    from app.migrate import upgrade

    upgrade(get_engine())


def _serve() -> None:
    import uvicorn

    from app.main import create_app

    _migrate()
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=8000,
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips=get_settings().forwarded_allow_ips,
    )


def _worker() -> None:
    from app.core.db import session_factory
    from app.jobs import worker

    # Every model is registered before the first query, so foreign keys resolve, and
    # every job handler before the first job is claimed.
    importlib.import_module("app.models")
    importlib.import_module("app.jobs.catalog").load()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker.run(session_factory(), get_settings(), stop)


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password (12 characters or more): ")
    if getpass.getpass("Again: ") != first:
        raise SystemExit("The two passwords differ. Nothing was created.")
    return first


def _create_owner(args: argparse.Namespace) -> int:
    from app.accounts.owner import OwnerExists, create_owner
    from app.core.db import session_factory
    from app.core.errors import ApiError

    importlib.import_module("app.models")
    _migrate()
    password = _read_password(args.password_stdin)
    with session_factory()() as session:
        try:
            user = create_owner(
                session,
                email=args.email,
                display_name=args.name,
                password=password,
                archive_name=args.archive,
            )
        except OwnerExists as exc:
            print(exc, file=sys.stderr)
            return 1
        except ApiError as exc:
            print(exc.message, file=sys.stderr)
            return 1
    print(f"Owner {user.email} created. Sign in at {get_settings().public_url}")
    return 0


def openapi_document() -> str:
    from app.main import create_app

    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memoir-cli", description=__doc__.split("\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "worker", "migrate", "openapi"):
        sub.add_parser(name)
    owner = sub.add_parser("create-owner", help="create the first account")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", required=True, help="the owner's display name")
    owner.add_argument("--archive", default="Our family", help="the archive's name")
    owner.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args(argv)
    configure(get_settings().log_level)
    if args.command == "openapi":
        sys.stdout.write(openapi_document())
    elif args.command == "create-owner":
        return _create_owner(args)
    else:
        {"serve": _serve, "worker": _worker, "migrate": _migrate}[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
