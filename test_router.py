import base64
import hashlib
import hmac
import json
import unittest

from router import EventDeduper, ReplyRouter, handle_webhook

SECRET = "test-secret"


class FakeClient:
    def __init__(self, reply_error=None):
        self.reply_error = reply_error
        self.sent = []

    def reply(self, token, text):
        if self.reply_error:
            raise self.reply_error
        self.sent.append(("reply", token, text))

    def push(self, to, text):
        self.sent.append(("push", to, text))


def make_router(client, now):
    return ReplyRouter(client, threshold_sec=20.0, clock=lambda: now, log=lambda _msg: None)


def sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


def webhook_body(event_id: str) -> bytes:
    return json.dumps({"events": [{
        "type": "message",
        "webhookEventId": event_id,
        "replyToken": "rt-1",
        "source": {"type": "user", "userId": "U1"},
        "message": {"type": "text", "text": "hi"},
    }]}).encode()


class ReplyRouterTest(unittest.TestCase):
    def test_reply_when_within_threshold(self):
        client = FakeClient()
        route = make_router(client, now=105.0).respond(100.0, "rt-1", "U1", "ok")
        self.assertEqual(route, "reply")
        self.assertEqual(client.sent, [("reply", "rt-1", "ok")])

    def test_push_when_threshold_exceeded(self):
        client = FakeClient()
        route = make_router(client, now=130.0).respond(100.0, "rt-1", "U1", "ok")
        self.assertEqual(route, "push")
        self.assertEqual(client.sent, [("push", "U1", "ok")])

    def test_push_fallback_when_reply_fails(self):
        client = FakeClient(reply_error=RuntimeError("400: Invalid reply token."))
        router = make_router(client, now=105.0)
        route = router.respond(100.0, "rt-1", "U1", "ok")
        self.assertEqual(route, "reply_failed_then_push")
        self.assertEqual(client.sent, [("push", "U1", "ok")])
        self.assertEqual(router.counts["reply_failed_then_push"], 1)


class HandleWebhookTest(unittest.TestCase):
    def test_redelivered_event_is_ignored(self):
        calls = []
        deduper = EventDeduper()
        body = webhook_body("evt-1")
        for _ in range(2):
            status = handle_webhook(body, sign(body), SECRET, deduper, lambda *a: calls.append(a))
            self.assertEqual(status, 200)
        self.assertEqual(len(calls), 1)

    def test_invalid_signature_returns_401(self):
        calls = []
        body = webhook_body("evt-2")
        status = handle_webhook(body, "invalid", SECRET, EventDeduper(), lambda *a: calls.append(a))
        self.assertEqual(status, 401)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
