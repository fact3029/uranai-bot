# 月詠の占い（LINE・Web 対応 AI占いbot）

タロット（大アルカナ22枚）と12星座占いを、Claude API が鑑定文にします。
1つのサーバー（FastAPI）で Web サイトと LINE 公式アカウントの両方に対応します。

## 料金プラン（収益の仕組み）

| | 無料 | プレミアム（月額・Stripe） |
|---|---|---|
| 12星座の今日の運勢 | 何度でも | 何度でも |
| タロット1枚 | 1日1回 | 1日10回まで |
| 3枚引き（過去・現在・未来） | × | ○ |
| 悩み相談つき個別鑑定 | × | ○ |

- 星座占いは「1日×12星座」で1回ずつだけAIを呼び、結果を使い回すので、利用者が増えても費用はほぼ増えません（集客用）。
- タロットは1回ごとにAIを呼ぶので、回数上限で費用を抑えます（`FREE_DAILY_LIMIT` / `PREMIUM_DAILY_LIMIT`）。
- カードを引くのはプログラム側の乱数で、AIには結果だけを渡します（AIが勝手にカードを変えないため）。

## ガチャ演出とシェア（Web）

- カードを引くとすぐ演出が始まり、その間にAIが鑑定文を書きます（`/api/tarot/draw` → `/api/tarot/read`）。
- カードごとにレア度（N 50% / R 30% / SR 15% / SSR 4% / UR 1%）が付き、光の色が段階的に上がる「昇格演出」→タップでめくる→紙吹雪と振動、の順に進みます。
- レア度は見た目だけで、運勢の良し悪しやお金とは関係ありません。確率は画面に表示しています。
- 結果は縦長画像（1080×1920）にしてシェアでき、X への投稿ボタンもあります。
- 端末で「視差効果を減らす」設定が入っている人には動きを抑えます。

## 動かし方

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # 値を入れる
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`ANTHROPIC_API_KEY` が空でも定型文で動くので、まず画面と流れを確認できます。

テスト: `.venv/bin/pip install pytest && .venv/bin/python -m pytest -q`

## LINE の設定

1. LINE Developers で Messaging API チャネルを作る
2. チャネルシークレットと長期アクセストークンを `.env` に入れる
3. Webhook URL に `https://<公開URL>/line/callback` を設定し、Webhook をオンにする（応答メッセージはオフ）

LINE で使える言葉: `タロット` / `星座 3/21` / `星座` / `3枚` / `相談 ○○` / `プレミアム`

## Stripe（月額課金）の設定

1. Stripe で月額の商品と価格を作り、価格ID（`price_...`）を `STRIPE_PRICE_ID` に入れる
2. Webhook の送り先に `https://<公開URL>/stripe/webhook` を登録し、
   `checkout.session.completed` / `customer.subscription.updated` / `customer.subscription.deleted` を選ぶ
3. 署名シークレット（`whsec_...`）を `STRIPE_WEBHOOK_SECRET` に入れる

## 公開前にやること

- `app/static/legal.html`（特定商取引法に基づく表記）を自分の情報で埋める
- 利用規約・プライバシーポリシーを用意する（LINEのユーザーIDと誕生日を保存しています）
- HTTPS で公開する（LINE と Stripe の Webhook は HTTPS が必要）

## 今の制限

- Web 版の利用者はブラウザの Cookie で見分けています。Cookie を消すと無料回数がリセットされ、Web で払った会員状態も引き継げません。本格運用ではログイン機能が必要です。
- データは SQLite 1ファイルです。サーバーを複数台にする時は PostgreSQL などに移してください。

## ファイル構成

- `app/main.py` Web と Webhook の入口
- `app/service.py` 回数制限・有料機能の判定（LINE と Web で共通）
- `app/reader.py` Claude API で鑑定文を作る（失敗時は定型文）
- `app/tarot.py` / `app/zodiac.py` カード（レア度を含む）と星座の計算
- `app/line.py` LINE の署名確認・返信・コマンド
- `app/billing.py` Stripe の申し込みと Webhook
- `app/store.py` SQLite
- `app/static/` Web 画面
