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
        return SimpleNamespace(checked=2, synced=2, failed=0, failures=[])

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


# --- OWNER'ga ogohlantirishlar (Ombor /system-alerts) ---
class _AlertRecorder:
    def __init__(self):
        self.alerts = []

    async def __call__(self, ombor, key, level, message):
        self.alerts.append((key, level, message))
        return True


def _patch(monkeypatch, results):
    it = iter(results)

    async def fake_sync(config, ombor, state):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    rec = _AlertRecorder()
    monkeypatch.setattr(main, "sync_once", fake_sync)
    monkeypatch.setattr(main, "send_alert", rec)
    return rec


async def _noop(_):
    return None


def _ok(checked=0, failures=()):
    return SimpleNamespace(checked=checked, synced=checked - len(failures), failed=len(failures),
                           failures=list(failures))


@pytest.mark.asyncio
async def test_alert_after_three_failures_once_then_recovered(monkeypatch):
    err = HRClientError("HR 404: Application not found")
    rec = _patch(monkeypatch, [err, err, err, err, _ok(), _ok()])
    await main.run_forever(SimpleNamespace(poll_interval_seconds=1), object(), None, sleep=_noop, max_cycles=6)
    assert [(k, lvl) for k, lvl, _ in rec.alerts] == [
        ("production-sync:cycle", "error"),       # 3-xatoda, 4-da takror yo'q
        ("production-sync:cycle", "recovered"),
    ]
    assert "3 marta ketma-ket" in rec.alerts[0][2] and "Application not found" in rec.alerts[0][2]


@pytest.mark.asyncio
async def test_two_failures_do_not_alert(monkeypatch):
    err = RuntimeError("x")
    rec = _patch(monkeypatch, [err, err, _ok()])
    await main.run_forever(SimpleNamespace(poll_interval_seconds=1), object(), None, sleep=_noop, max_cycles=3)
    assert rec.alerts == []


@pytest.mark.asyncio
async def test_event_failures_reported_then_recovered(monkeypatch):
    fails = [("produced:plan_task:191", "400: Yetarli xomashyo yo'q")]
    rec = _patch(monkeypatch, [_ok(1, fails), _ok(1, fails), _ok(1), _ok(0)])
    await main.run_forever(SimpleNamespace(poll_interval_seconds=1), object(), None, sleep=_noop, max_cycles=4)
    levels = [(k, lvl) for k, lvl, _ in rec.alerts]
    # Har tsiklda yuboriladi - takrorni Ombor to'xtatadi (bir xil matn)
    assert levels == [("production-sync:events", "warning"), ("production-sync:events", "warning"),
                      ("production-sync:events", "recovered")]
    assert rec.alerts[0][2] == rec.alerts[1][2]
    assert "produced:plan_task:191" in rec.alerts[0][2]


def test_events_message_is_stable_and_limited():
    from app.alerts import events_message
    a = [("k2", "r2"), ("k1", "r1")]
    assert events_message(a) == events_message(list(reversed(a)))
    many = [(f"k{i:02d}", "r") for i in range(15)]
    assert "… va yana 5 ta" in events_message(many)


@pytest.mark.asyncio
async def test_send_alert_never_raises():
    import httpx
    from erp_bridge_kit import ModuleClient, OmborBridgeClient

    from app.alerts import send_alert

    def boom(request):
        raise httpx.ConnectError("Ombor ishlamayapti")

    broken = OmborBridgeClient(ModuleClient("http://ombor.test", transport=httpx.MockTransport(boom)))
    assert await send_alert(broken, "k", "error", "m") is False
    assert await send_alert(None, "k", "error", "m") is False


@pytest.mark.asyncio
async def test_send_alert_posts_to_ombor():
    import json

    import httpx
    from erp_bridge_kit import ModuleClient, OmborBridgeClient

    from app.alerts import send_alert
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "a1", "notified": True})

    ombor = OmborBridgeClient(ModuleClient("http://ombor.test", transport=httpx.MockTransport(handler)))
    assert await send_alert(ombor, "production-sync:cycle", "error", "xato") is True
    assert seen["path"] == "/system-alerts"
    assert seen["body"] == {"source": "production-sync", "key": "production-sync:cycle",
                            "level": "error", "message": "xato"}
