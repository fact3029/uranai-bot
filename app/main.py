"""Web サイトと LINE の Webhook を1つのサーバーで動かす。

起動: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
import logging
import secrets
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import billing, line, zodiac
from .config import settings
from .service import FortuneService, today_jst
from .store import Store

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="月詠の占い")
service = FortuneService(Store(settings.db_path))


def web_user(request: Request, response: Response) -> str:
    uid = request.cookies.get("uid")
    if not uid or len(uid) > 64:
        uid = secrets.token_urlsafe(24)
        response.set_cookie("uid", uid, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return f"web:{uid}"


class TarotIn(BaseModel):
    count: int = Field(1, description="1 または 3")
    question: str = Field("", max_length=500)


class HoroscopeIn(BaseModel):
    birthday: str = Field(..., max_length=20)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/legal")
def legal():
    return FileResponse(STATIC / "legal.html")


@app.get("/api/me")
def me(request: Request, response: Response):
    uid = web_user(request, response)
    return {
        "premium": service.store.is_premium(uid),
        "used": service.store.used_today(uid, today_jst()),
        "limit": service.daily_limit(uid),
        "billing": settings.billing_enabled,
    }


@app.post("/api/tarot")
def api_tarot(body: TarotIn, request: Request, response: Response):
    if body.count not in (1, 3):
        raise HTTPException(400, "count は 1 か 3")
    r = service.tarot(web_user(request, response), body.count, body.question)
    return {"ok": r.ok, "text": r.text, "reason": r.reason, "cards": r.cards}


@app.post("/api/horoscope")
def api_horoscope(body: HoroscopeIn):
    bd = zodiac.parse_birthday(body.birthday)
    if not bd:
        raise HTTPException(400, "誕生日は 3/21 や 1990-03-21 の形で入力してください")
    r = service.horoscope(*bd)
    return {"ok": True, "text": r.text, "sign": zodiac.sign_of(*bd)}


@app.post("/billing/checkout")
def checkout(request: Request, response: Response):
    url = billing.checkout_url(web_user(request, response))
    if not url:
        raise HTTPException(503, "課金は未設定です")
    return {"url": url}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        billing.handle_webhook(payload, request.headers.get("stripe-signature", ""), service.store)
    except Exception:
        logging.exception("Stripe webhook の検証に失敗")
        raise HTTPException(400, "invalid webhook")
    return {"ok": True}


@app.post("/line/callback")
async def line_callback(request: Request, tasks: BackgroundTasks):
    body = await request.body()
    if not line.verify_signature(body, request.headers.get("x-line-signature", ""), settings.line_channel_secret):
        raise HTTPException(400, "invalid signature")
    events = (await request.json()).get("events", [])
    # AI の応答待ちで LINE 側がタイムアウトしないよう、先に 200 を返して裏で処理する
    tasks.add_task(line.handle_events, service, events)
    return {"ok": True}
