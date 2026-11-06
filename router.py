"""LINE webhook の受信処理と、reply / push の切り替え。外部ライブラリなし (Python 3.9+)。"""

import base64
import hashlib
import hmac
import json
import time
from collections import OrderedDict


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """X-Line-Signature (本文の HMAC-SHA256 を Base64 にしたもの) を検証する。"""
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature or "")


class EventDeduper:
    """webhookEventId で再送を弾く。古い ID から捨てる (メモリ上限つき)。"""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._seen = OrderedDict()

    def first_time(self, event_id: str) -> bool:
        if not event_id:
            return True  # ID が無いイベントは判定できないので通す
        if event_id in self._seen:
            return False
        self._seen[event_id] = True
        if len(self._seen) > self.max_size:
            self._seen.popitem(last=False)
        return True


class ReplyRejected(Exception):
    """LINE が reply を 4xx で拒否した (期限切れ・使用済みなど)。未配信が確定している。"""


class ReplyRouter:
    """受信時刻からの経過秒が threshold_sec 未満なら reply、以上なら push。"""

    def __init__(self, client, threshold_sec: float = 20.0, clock=time.monotonic, log=print):
        self.client = client
        self.threshold_sec = threshold_sec
        self.clock = clock
        self.log = log
        self.counts = {"reply": 0, "push": 0, "reply_failed_then_push": 0, "reply_unknown": 0}

    def respond(self, received_at: float, reply_token: str, user_id: str, text: str) -> str:
        elapsed = self.clock() - received_at
        if elapsed < self.threshold_sec:
            try:
                self.client.reply(reply_token, text)
                return self._done("reply", elapsed)
            except ReplyRejected as e:  # 未配信が確定。token は二度と使えないので push へ
                self.log(f"reply rejected after {elapsed:.1f}s: {e}")
                self.client.push(user_id, text)
                return self._done("reply_failed_then_push", elapsed)
            except Exception as e:  # タイムアウト・5xx 等。届いた可能性があるので push しない
                self.log(f"reply result unknown after {elapsed:.1f}s: {e}")
                return self._done("reply_unknown", elapsed)
        self.client.push(user_id, text)
        return self._done("push", elapsed)

    def _done(self, route: str, elapsed: float) -> str:
        self.counts[route] += 1
        self.log(f"route={route} elapsed={elapsed:.1f}s")
        return route


def push_target(source: dict) -> str:
    """push の宛先。グループ / トークルームならそちらへ、1:1 ならユーザーへ。"""
    return source.get("groupId") or source.get("roomId") or source.get("userId", "")


def handle_webhook(body: bytes, signature: str, channel_secret: str, deduper: EventDeduper,
                   dispatch, clock=time.monotonic) -> int:
    """webhook 1 回分を処理して HTTP ステータスを返す。

    署名が不正なら 401。正しければテキストメッセージを dispatch に渡して 200。
    dispatch は (received_at, reply_token, to, text) を受け取り、すぐ戻ること
    (LLM 呼び出しは dispatch の先で別スレッドに逃がす)。
    """
    received_at = clock()
    if not verify_signature(channel_secret, body, signature):
        return 401
    payload = json.loads(body.decode("utf-8"))
    for event in payload.get("events", []):
        if not deduper.first_time(event.get("webhookEventId", "")):
            continue
        message = event.get("message", {})
        if event.get("type") != "message" or message.get("type") != "text":
            continue
        dispatch(received_at, event.get("replyToken", ""), push_target(event.get("source", {})),
                 message.get("text", ""))
    return 200
