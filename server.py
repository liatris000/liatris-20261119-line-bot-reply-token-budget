"""LINE webhook サーバー。受けたら即 200 を返し、返信は別スレッドで作る。

    LINE_CHANNEL_SECRET=... LINE_CHANNEL_ACCESS_TOKEN=... python3 server.py

generate_reply() は LLM 呼び出しの差し替え位置。既定は FAKE_LLM_DELAY_SEC 秒待って
オウム返しするだけなので、待ち時間を変えて reply / push の切り替えを試せる。
"""

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from router import EventDeduper, ReplyRouter, handle_webhook

API = "https://api.line.me/v2/bot/message"
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
THRESHOLD = float(os.environ.get("REPLY_THRESHOLD_SEC", "20"))
FAKE_DELAY = float(os.environ.get("FAKE_LLM_DELAY_SEC", "0"))


class LineClient:
    def _post(self, path: str, payload: dict) -> None:
        req = urllib.request.Request(
            f"{API}/{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"},
            method="POST",
        )
        # 4xx / 5xx は urllib.error.HTTPError として送出され、ReplyRouter が push に回す
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()

    def reply(self, reply_token: str, text: str) -> None:
        self._post("reply", {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]})

    def push(self, to: str, text: str) -> None:
        self._post("push", {"to": to, "messages": [{"type": "text", "text": text}]})


def generate_reply(text: str) -> str:
    """ここを LLM 呼び出しに差し替える。"""
    time.sleep(FAKE_DELAY)
    return f"echo: {text}"


router = ReplyRouter(LineClient(), threshold_sec=THRESHOLD)
deduper = EventDeduper()
dedupe_lock = threading.Lock()  # 受信スレッド間で deduper を守る
route_lock = threading.Lock()  # 返信スレッド間で router.counts を守る


def dispatch(received_at: float, reply_token: str, to: str, text: str) -> None:
    def work():
        answer = generate_reply(text)
        with route_lock:
            router.respond(received_at, reply_token, to, answer)

    threading.Thread(target=work, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with dedupe_lock:
            status = handle_webhook(body, self.headers.get("X-Line-Signature", ""),
                                    CHANNEL_SECRET, deduper, dispatch)
        self.send_response(status)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"listening on :{port}/callback (threshold={THRESHOLD}s)")
    ThreadingHTTPServer(("", port), Handler).serve_forever()
