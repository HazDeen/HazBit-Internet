from __future__ import annotations

import logging
import traceback
from collections.abc import Iterator

import httpx
import pytest
import structlog
from app.core.config import Settings
from app.core.logging import configure_logging, get_logger, redact_telegram_tokens
from app.modules.bots.telegram_api import TelegramApiError, TelegramBotClient

TOKEN = "123456789:synthetic_TEST_token-123"
URL = f"https://api.telegram.org/bot{TOKEN}/getMe"


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    config = structlog.get_config().copy()
    yield
    root.handlers = handlers
    root.setLevel(level)
    structlog.configure(**config)


@pytest.mark.parametrize("url", [URL, URL.replace(":synthetic", "%3Asynthetic")])
def test_redacts_bot_url(url: str) -> None:
    assert "synthetic_TEST" not in redact_telegram_tokens(url)
    assert redact_telegram_tokens(url).endswith("[REDACTED]/getMe")


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_httpx_and_exception_logs_redact_tokens(
    test_settings: Settings,
    capsys: pytest.CaptureFixture[str],
    log_format: str,
) -> None:
    settings = test_settings.model_copy(update={"log_format": log_format})
    configure_logging(settings)
    logging.getLogger("httpx").info("HTTP Request: POST %s", URL)
    get_logger().info("telegram_test", url=URL)
    try:
        raise RuntimeError(f"HTTP error for {URL}")
    except RuntimeError:
        logging.getLogger("httpx").exception("Failed")
    output = capsys.readouterr().out
    assert TOKEN not in output
    assert "[REDACTED]/getMe" in output
    assert "RuntimeError" in output


@pytest.mark.parametrize("failure", ["status", "network", "json", "body", "description"])
async def test_raw_cli_tracebacks_cannot_leak_token(failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "network":
            raise httpx.ConnectError(f"Cannot reach {request.url}", request=request)
        if failure == "status":
            return httpx.Response(401)
        if failure == "json":
            return httpx.Response(200, text="invalid JSON")
        if failure == "body":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"ok": False, "description": f"Failure {TOKEN}"})

    bot = TelegramBotClient(TOKEN, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TelegramApiError) as caught:
            await bot.call("getMe", {})
        assert TOKEN not in "".join(traceback.format_exception(caught.value))
    finally:
        await bot.close()
