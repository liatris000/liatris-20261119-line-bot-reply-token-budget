# line-bot-reply-token-budget

LLM を挟んだ LINE ボットで、受信からの経過時間を測って reply / push を切り替える最小実装。外部ライブラリなしの Python 3。

記事: https://zenn.dev/liatris/articles/20261119-line-bot-reply-token-budget

## ファイル

- `router.py` — 署名検証（`X-Line-Signature`）、`webhookEventId` による再送の重複排除、reply / push を切り替える `ReplyRouter`
- `server.py` — webhook を受けて即 200 を返し、返信は別スレッドで作るサーバー。`generate_reply()` を LLM 呼び出しに差し替えて使う
- `test_router.py` — 分岐ロジックのテスト（5 本）

## 動かす

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

閾値 20 秒は実測値ではなく仮置き。reply token の実際の寿命は測っていない。

ログの `route=reply` / `route=push` / `route=reply_failed_then_push` を集計すると、閾値が攻めすぎか（`reply_failed_then_push` が出る）、慎重すぎるか（`push` ばかり）を判断できる。
