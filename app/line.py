"""LINE Messaging API: 署名確認・返信・コマンド解釈。"""
import base64
import hashlib
import hmac
import logging

import httpx

from . import billing, zodiac
from .config import settings
from .service import FortuneService

log = logging.getLogger(__name__)
REPLY_URL = "https://api.line.me/v2/bot/message/reply"
MAX_TEXT = 5000

HELP = """🔮 月詠の占いメニュー

・「タロット」… 今日の1枚（無料・1日1回）
・「星座 3/21」… 誕生日から今日の星座占い（無料）
・「星座」… 登録した誕生日で星座占い
・「3枚」… 過去・現在・未来の3枚引き（プレミアム）
・「相談 ○○」… 悩みに合わせた個別鑑定（プレミアム）
・「プレミアム」… 有料プランのご案内"""


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def reply(reply_token: str, texts: list[str]) -> None:
    messages = [{"type": "text", "text": t[:MAX_TEXT]} for t in texts[:5]]
    r = httpx.post(
        REPLY_URL,
        headers={"Authorization": f"Bearer {settings.line_access_token}"},
        json={"replyToken": reply_token, "messages": messages},
        timeout=10,
    )
    if r.status_code != 200:
        log.error("LINE 返信失敗 status=%s body=%s", r.status_code, r.text[:200])


RARITY_MARK = {"UR": "🌈🌈🌈", "SSR": "🌟🌟", "SR": "✨", "R": "🔹", "N": "▫️"}


def _tarot_reply(service: FortuneService, uid: str, r) -> list[str]:
    if not r.ok:
        return [r.text, _premium_text(service, uid)] if r.reason == "premium_only" else [r.text]
    head = "\n".join(f"{RARITY_MARK.get(c['rarity'], '')}【{c['rarity']}】{c['position']}: {c['label']}" for c in r.cards)
    return [head, r.text]


def respond(service: FortuneService, user_id: str, text: str) -> list[str]:
    """受け取った文に対する返信文を作る（送信はしない）。"""
    t = text.strip()
    uid = f"line:{user_id}"

    if t in ("タロット", "占って", "今日の運勢", "1枚"):
        return _tarot_reply(service, uid, service.tarot(uid, 1))
    if t in ("3枚", "三枚", "3枚引き"):
        return _tarot_reply(service, uid, service.tarot(uid, 3))
    if t.startswith("相談"):
        question = t[2:].strip(" :：　")
        if not question:
            return ["「相談 」のあとに悩みを書いて送ってください。\n例: 相談 転職するか迷っています"]
        return _tarot_reply(service, uid, service.tarot(uid, 3, question))
    if t.startswith(("星座", "誕生日")):
        bd = zodiac.parse_birthday(t)
        if bd:
            service.store.set_birthday(uid, *bd)
        else:
            bd = service.store.birthday(uid)
        if not bd:
            return ["誕生日を添えて送ってください。\n例: 星座 3/21"]
        return [service.horoscope(*bd).text]
    if t in ("プレミアム", "課金", "有料"):
        return [_premium_text(service, uid)]
    return [HELP]


def _premium_text(service: FortuneService, uid: str) -> str:
    if service.store.is_premium(uid):
        return "すでにプレミアム会員です。いつもありがとうございます🌙"
    url = billing.checkout_url(uid)
    if not url:
        return "プレミアムプランは準備中です。"
    return f"✨ プレミアムプラン\n・3枚引き\n・悩み相談つきの個別鑑定\n・1日{settings.premium_daily_limit}回まで\n\nお申し込みはこちら:\n{url}"


def handle_events(service: FortuneService, events: list[dict]) -> None:
    for ev in events:
        try:
            token = ev.get("replyToken")
            user_id = (ev.get("source") or {}).get("userId")
            if not token or not user_id:
                continue
            if ev.get("type") == "follow":
                reply(token, ["友だち追加ありがとうございます🌙\n占い師の月詠です。\n\n" + HELP])
            elif ev.get("type") == "message" and (ev.get("message") or {}).get("type") == "text":
                reply(token, respond(service, user_id, ev["message"]["text"]))
        except Exception:
            log.exception("LINE イベント処理に失敗")
