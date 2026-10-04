"""memoir-cli: the commands the images run.

memoir-cli serve      migrate, then serve the API on :8000
memoir-cli worker     run the job worker until stopped
memoir-cli migrate    apply the database migrations
memoir-cli openapi    print the OpenAPI document (the web client is built from it)
"""

import argparse
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
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, log_config=None)


def _worker() -> None:
    from app.core.db import session_factory
    from app.jobs import worker

    # Every model is registered before the first query, so foreign keys resolve.
    importlib.import_module("app.models")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker.run(session_factory(), get_settings(), stop)


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
    args = parser.parse_args(argv)
    configure(get_settings().log_level)
    if args.command == "openapi":
        sys.stdout.write(openapi_document())
    else:
        {"serve": _serve, "worker": _worker, "migrate": _migrate}[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
