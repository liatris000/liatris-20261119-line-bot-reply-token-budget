# line-bot-reply-token-budget

LLM を挟んだ LINE ボットで、受信からの経過時間を測って reply / push を切り替える最小実装。外部ライブラリなしの Python 3。

## 前提

Python 3.11 以上。外部ライブラリなし。サーバーを LINE につなぐときは、チャネルのシークレットとアクセストークンが要る。

## ファイル

- `router.py` — 署名検証（`X-Line-Signature`）、`webhookEventId` による再送の重複排除、reply / push を切り替える `ReplyRouter`
- `server.py` — webhook を受けて即 200 を返し、返信は別スレッドで作るサーバー。`generate_reply()` を LLM 呼び出しに差し替えて使う
- `test_router.py` — 分岐ロジックのテスト（6 本）

## 動かし方

```bash
python3 -m unittest -v test_router

LINE_CHANNEL_SECRET=... LINE_CHANNEL_ACCESS_TOKEN=... \
REPLY_THRESHOLD_SEC=20 FAKE_LLM_DELAY_SEC=0 python3 server.py   # POST /callback
```

| 環境変数 | 既定 | 意味 |
|---|---|---|
| `REPLY_THRESHOLD_SEC` | 20 | 受信からこの秒数未満なら reply、以上なら push |
| `FAKE_LLM_DELAY_SEC` | 0 | スタブの `generate_reply()` が待つ秒数。切り替えの確認用 |
| `PORT` | 8000 | 待ち受けポート |

## 期待される出力

テストは 6 本とも通る。

```text
test_invalid_signature_returns_401 ... ok
test_redelivered_event_is_ignored ... ok
test_no_push_when_reply_result_unknown ... ok
test_push_fallback_when_reply_fails ... ok
test_push_when_threshold_exceeded ... ok
test_reply_when_within_threshold ... ok

Ran 6 tests

OK
```

## 設計

push に回すのは、LINE が reply を 4xx で拒否して未配信が確定したときだけ。タイムアウトや 5xx は届いた可能性があるので push せず、`route=reply_unknown` として記録する（二重送信を避けるため）。

ログの `route=reply` / `route=push` / `route=reply_failed_then_push` / `route=reply_unknown` を集計すると、閾値が攻めすぎか（`reply_failed_then_push` が出る）、慎重すぎるか（`push` ばかり）を判断できる。

## 確かめていない範囲

- 閾値 20 秒は実測値ではなく仮置き。reply token の実際の寿命は測っていない。
- 実際の LINE のチャネルにつないでの動作(サーバーの起動と署名つきの POST)は確かめていない

## 記事

https://zenn.dev/liatris/articles/20261119-line-bot-reply-token-budget
