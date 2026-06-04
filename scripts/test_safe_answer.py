"""Tests for safe_answer retry behavior."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiogram.exceptions import TelegramNetworkError

import bot


class _FakeMessage:
    def __init__(self) -> None:
        self.chat = MagicMock(id=12345)
        self.answer = AsyncMock()


async def test_safe_answer_success_first_try() -> None:
    message = _FakeMessage()
    ok = await bot.safe_answer(message, "hello")
    assert ok is True
    assert message.answer.await_count == 1


async def test_safe_answer_retries_then_succeeds() -> None:
    message = _FakeMessage()
    message.answer.side_effect = [
        asyncio.TimeoutError(),
        TelegramNetworkError(method="sendMessage", message="network"),
        None,
    ]
    ok = await bot.safe_answer(message, "hello")
    assert ok is True
    assert message.answer.await_count == 3


async def test_safe_answer_all_retries_fail() -> None:
    message = _FakeMessage()
    message.answer.side_effect = asyncio.TimeoutError()
    ok = await bot.safe_answer(message, "hello")
    assert ok is False
    assert message.answer.await_count == 4


async def test_safe_answer_non_retriable_error() -> None:
    message = _FakeMessage()
    message.answer.side_effect = ValueError("bad request")
    ok = await bot.safe_answer(message, "hello")
    assert ok is False
    assert message.answer.await_count == 1


async def run_all() -> None:
    await test_safe_answer_success_first_try()
    await test_safe_answer_retries_then_succeeds()
    await test_safe_answer_all_retries_fail()
    await test_safe_answer_non_retriable_error()
    print("safe_answer tests passed")


if __name__ == "__main__":
    asyncio.run(run_all())
