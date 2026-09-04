from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

import uvicorn

from autometa.config import Settings, get_settings


LOGGER = logging.getLogger(__name__)
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def build_uvicorn_options(settings: Settings) -> dict[str, object]:
    return {"host": settings.autometa_host, "port": settings.autometa_port}


def serve() -> None:
    settings = get_settings()
    options = build_uvicorn_options(settings)
    if options["host"] not in _LOOPBACK_HOSTS:
        LOGGER.warning(
            "AutoMeta is listening beyond localhost without authentication."
        )
    uvicorn.run("autometa.api.main:app", reload=False, **options)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autometa")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Start the local AutoMeta Uvicorn server")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        serve()
