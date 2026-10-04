"""Every module that registers job handlers. The worker imports them all at start."""

import importlib

MODULES = ("app.domain.purge", "app.capture.jobs")


def load() -> None:
    for name in MODULES:
        importlib.import_module(name)
