"""Asosiy sikl: vaqtincha xato servisni yiqitmasligi kerak."""
from types import SimpleNamespace

import pytest

import app.main as main
from app.hr_reader import HRClientError


@pytest.mark.asyncio
async def test_transient_hr_error_does_not_crash_and_recovers(monkeypatch):
    calls = {"n": 0}

    async def flaky_sync(config, ombor, state):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise HRClientError('HR 404: {"message":"Application not found"}')
        return SimpleNamespace(checked=2, synced=2, failed=0)

    monkeypatch.setattr(main, "sync_once", flaky_sync)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    config = SimpleNamespace(poll_interval_seconds=300)
    await main.run_forever(config, None, None, sleep=fake_sleep, max_cycles=5)

    assert calls["n"] == 5  # xatolardan keyin ham davom etdi
    assert sleeps == [300, 600, 900, 300, 300]  # backoff, tiklangach odatdagi oraliq


@pytest.mark.asyncio
async def test_backoff_is_capped(monkeypatch):
    async def always_fail(config, ombor, state):
        raise RuntimeError("tarmoq yo'q")

    monkeypatch.setattr(main, "sync_once", always_fail)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    await main.run_forever(SimpleNamespace(poll_interval_seconds=300), None, None,
                           sleep=fake_sleep, max_cycles=6)
    assert sleeps == [300, 600, 900, 900, 900, 900]


@pytest.mark.asyncio
async def test_cancellation_still_stops_the_loop(monkeypatch):
    import asyncio

    async def cancelled(config, ombor, state):
        raise asyncio.CancelledError()

    monkeypatch.setattr(main, "sync_once", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await main.run_forever(SimpleNamespace(poll_interval_seconds=1), None, None, max_cycles=1)
