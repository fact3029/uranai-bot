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

## SNS 自動投稿（social/）

毎朝 6:43（日本時間）に GitHub Actions が動き、次の3つを作って各SNSに投稿します。

| 作るもの | サイズ | 投稿先 |
|---|---|---|
| 12星座ランキング画像 | 1080×1350 | X・Threads・Instagram（2枚組）・LINE |
| みんなの今日の1枚（画像） | 1080×1350 | X・Threads・Instagram（2枚組） |
| ガチャ演出の縦長動画（約9.5秒） | 1080×1920 | YouTube ショート・Instagram リール・TikTok（手動） |

- ランキングとカードは日付から決まるので、LINE bot の星座占いと同じ結果になります。
- AI（Claude）は短い一言だけ書きます。APIキーが無い・失敗した時は定型文になります。
- 1つのSNSで失敗しても他は続けます。結果は Actions の実行記録と `summary.json` に残ります。
- 作った画像・動画・投稿文は Actions の「Artifacts」から7日間ダウンロードできます。

### 試し方

```bash
python -m social.daily --dry-run --out out   # 作るだけ（投稿しない）
python -m social.daily --only x              # X だけ投稿
```

GitHub の Actions 画面から「毎朝の占い自動投稿」→「Run workflow」で、投稿先を絞ったり作るだけにしたりもできます。

### 設定（GitHub の Settings → Secrets and variables → Actions）

設定が無いSNSは自動で飛ばすので、できたところから順に足せます。

| 投稿先 | Secrets | 準備すること |
|---|---|---|
| 共通 | `ANTHROPIC_API_KEY` | 無くても定型文で動く |
| 画像の置き場 | `S3_ENDPOINT_URL` `S3_BUCKET` `S3_ACCESS_KEY_ID` `S3_SECRET_ACCESS_KEY` `MEDIA_PUBLIC_BASE_URL` | Cloudflare R2 など S3 互換の置き場を作り、公開URLで見られるようにする。Threads・Instagram・LINE は URL からしか画像を受け取らないため必要 |
| X | `X_API_KEY` `X_API_SECRET` `X_ACCESS_TOKEN` `X_ACCESS_TOKEN_SECRET` | 開発者登録してアプリを作り、読み書き権限のアクセストークンを発行。従量課金なので残高（クレジット）を入れておく |
| Threads | `THREADS_USER_ID` `THREADS_ACCESS_TOKEN` | Meta の開発者アプリで Threads API を使い、長期トークンを発行 |
| Instagram | `IG_USER_ID` `IG_ACCESS_TOKEN` | プロアカウントにして Facebook ページとつなぎ、`instagram_content_publish` 権限のトークンを発行 |
| YouTube | `YT_CLIENT_ID` `YT_CLIENT_SECRET` `YT_REFRESH_TOKEN` | Google Cloud で YouTube Data API を有効にし、OAuth でリフレッシュトークンを取得 |
| LINE | `LINE_CHANNEL_ACCESS_TOKEN`、変数 `LINE_BROADCAST_WEEKDAYS`（例 `4` = 金曜だけ） | 一斉配信は無料枠を「配信回数×友だち数」で使うので曜日を絞る |

### 先に知っておくこと

- **TikTok は自動投稿にしていません。** 審査前のアプリからの投稿は自分だけが見られる設定に限られ、審査では投稿前に本人が確認する画面が求められるためです。毎朝できる動画（Artifacts の `gacha.mp4`）と投稿文（`captions.txt`）を使って手動で投稿してください。
- **YouTube は審査が通るまで非公開になります。** 2020年7月28日以降に作った未審査の Google Cloud プロジェクトからの投稿は非公開に限られます。審査（監査）を申し込んでください。
- **X は有料です。** 2026年2月から新規の開発者は従量課金で、投稿1件あたり約0.015ドル（リンク付きは約0.20ドル）とされています（公式の料金ページで要確認）。この仕組みはリンクを付けずに1日1投稿（画像2枚）です。画像アップロードの料金は未確認です。
- **Instagram・Threads のトークンには期限があります。** 長期トークンも期限が来たら更新が必要です（自動更新はまだ入れていません）。
- **二重投稿の防止:** 同じ時間に2回は走らないようにしていますが、手動で再実行すると同じ日の投稿がもう一度出ます。失敗したSNSだけを `--only` で選んでやり直してください。

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
- `social/` SNS 自動投稿（`content.py` 中身と投稿文 / `render.py` 画像と動画 / `posters.py` 各SNSへの投稿 / `daily.py` 毎朝の実行）
- `.github/workflows/daily-post.yml` 毎朝の実行設定
