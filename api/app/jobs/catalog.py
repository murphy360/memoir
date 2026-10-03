"""Every module that registers job handlers. The worker imports them all at start."""

import importlib

MODULES = (
    "app.domain.purge",
    "app.capture.jobs",
    "app.analysis.transcribe",
    "app.analysis.extract",
    "app.questions.generate",
)


def load() -> None:
    for name in MODULES:
        importlib.import_module(name)
