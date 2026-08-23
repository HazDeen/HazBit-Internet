from __future__ import annotations

import argparse
import asyncio
import secrets
from collections.abc import Sequence

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.modules.auth.email import EmailDeliveryError, create_email_sender
from app.operations.launch import LaunchError, bootstrap_launch, verify_launch_readiness


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hazbit production operations")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("bootstrap", help="create the initial catalog and super admin")
    subcommands.add_parser("preflight", help="verify database, Redis, catalog and admin")
    email = subcommands.add_parser("test-email", help="send an SMTP delivery test")
    email.add_argument("--to", help="recipient; defaults to the first super admin")
    return parser


async def _run(command: str, recipient: str | None) -> None:
    settings = get_settings()
    configure_logging(settings)
    logger = get_logger(component="operations", command=command)
    if command == "bootstrap":
        await bootstrap_launch(settings)
        logger.info("launch_bootstrap_complete")
        return
    if command == "preflight":
        await verify_launch_readiness(settings)
        logger.info("launch_preflight_complete")
        return
    if command == "test-email":
        target = recipient or settings.launch.super_admin_email
        if target is None:
            raise ValueError("test email recipient is required")
        address = str(TypeAdapter(EmailStr).validate_python(target))
        sender = create_email_sender(settings.auth.email)
        await sender.send_test(email=address, reference=secrets.token_hex(4).upper())
        logger.info("smtp_test_email_sent", recipient=address)
        return
    raise RuntimeError(f"unsupported command: {command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        asyncio.run(_run(args.command, getattr(args, "to", None)))
    except (EmailDeliveryError, LaunchError, ValidationError, ValueError) as exc:
        print(f"Hazbit operation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
