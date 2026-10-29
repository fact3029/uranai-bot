import base64
import hashlib
import hmac
import os
import random
from datetime import date
from types import SimpleNamespace

os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["DB_PATH"] = ":memory:"
os.environ["LINE_CHANNEL_SECRET"] = "test-secret"

import pytest  # noqa: E402

from app import line, reader, tarot, zodiac  # noqa: E402
from app.service import FortuneService, today_jst  # noqa: E402
from app.store import Store  # noqa: E402


# --- 星座 -----------------------------------------------------------------
@pytest.mark.parametrize("m,d,sign", [
    (1, 1, "やぎ座"), (1, 19, "やぎ座"), (1, 20, "みずがめ座"), (3, 20, "うお座"), (3, 21, "おひつじ座"),
    (7, 23, "しし座"), (11, 22, "さそり座"), (11, 23, "いて座"), (12, 21, "いて座"), (12, 22, "やぎ座"),
    (12, 31, "やぎ座"),
])
def test_sign_boundaries(m, d, sign):
    assert zodiac.sign_of(m, d) == sign


def test_parse_birthday():
    assert zodiac.parse_birthday("星座 3/21") == (3, 21)
    assert zodiac.parse_birthday("1990-03-21") == (3, 21)
    assert zodiac.parse_birthday("12月5日") == (12, 5)
    assert zodiac.parse_birthday("2/30") is None
    assert zodiac.parse_birthday("星座") is None


def test_daily_fortune_is_stable_and_ranking_complete():
    day = date(2026, 10, 28)
    assert zodiac.daily_fortune("しし座", day) == zodiac.daily_fortune("しし座", day)
    ranks = sorted(zodiac.daily_fortune(s, day)["rank"] for s in zodiac.SIGN_NAMES)
    assert ranks == list(range(1, 13))


# --- タロット -------------------------------------------------------------
def test_rarity_rates():
    assert abs(sum(p for _, p in tarot.RARITIES) - 1) < 1e-9
    rng = random.Random(0)
    got = [tarot.roll_rarity(rng) for _ in range(100_000)]
    for name, p in tarot.RARITIES:
        assert abs(got.count(name) / len(got) - p) < 0.01


def test_draw_unique_cards():
    cards = tarot.draw(3, random.Random(1))
    assert [c.position for c in cards] == ["過去", "現在", "未来"]
    assert len({c.name for c in cards}) == 3
    with pytest.raises(ValueError):
        tarot.draw(2)


# --- AI 応答（偽のクライアント）---------------------------------------------
class FakeClient:
    def __init__(self, text="鑑定文です", stop_reason="end_turn"):
        self.calls = []
        resp = SimpleNamespace(
            stop_reason=stop_reason, stop_details=None,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        )

        def create(**kwargs):
            self.calls.append(kwargs)
            return resp

        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


def test_reading_uses_drawn_cards_and_question():
    fake = FakeClient()
    cards = tarot.draw(1, random.Random(2))
    out = reader.tarot_reading(cards, "仕事の悩み", client=fake)
    assert out.startswith("鑑定文です") and reader.DISCLAIMER in out
    prompt = fake.calls[0]["messages"][0]["content"]
    assert cards[0].name in prompt and "仕事の悩み" in prompt
    assert fake.calls[0]["fallbacks"] == "default"


def test_refusal_falls_back_to_template():
    cards = tarot.draw(1, random.Random(3))
    out = reader.tarot_reading(cards, client=FakeClient(text="", stop_reason="refusal"))
    assert cards[0].name in out


# --- 回数制限と有料機能 -----------------------------------------------------
@pytest.fixture
def svc():
    return FortuneService(Store(":memory:"), client=FakeClient())


def test_free_limit_and_premium(svc):
    assert svc.tarot("u1").ok
    second = svc.tarot("u1")
    assert not second.ok and second.reason == "limit"
    assert svc.tarot("u1", 3).reason == "premium_only"
    assert svc.tarot("u1", 1, "相談").reason == "premium_only"

    svc.store.set_premium("u1", "sub_1", True)
    r = svc.tarot("u1", 3, "相談")
    assert r.ok and len(r.cards) == 3
    svc.store.deactivate_subscription("sub_1")
    assert not svc.store.is_premium("u1")


def test_draw_then_read_is_owner_only_and_cached(svc):
    d = svc.draw("u2")
    assert d.ok and d.draw_id and d.cards[0]["rarity"] in ("N", "R", "SR", "SSR", "UR")
    assert len(svc.client.calls) == 0  # 引くだけではAIを呼ばない
    assert svc.read("someone_else", d.draw_id).reason == "not_found"
    first = svc.read("u2", d.draw_id)
    again = svc.read("u2", d.draw_id)
    assert first.text == again.text and len(svc.client.calls) == 1
    assert d.cards[0]["name"] in svc.client.calls[0]["messages"][0]["content"]


def test_horoscope_cached_once_per_sign(svc):
    a = svc.horoscope(3, 21)
    b = svc.horoscope(4, 1)  # 同じおひつじ座
    assert a.text == b.text and len(svc.client.calls) == 1


# --- LINE -----------------------------------------------------------------
def test_line_signature():
    body = b'{"events":[]}'
    sig = base64.b64encode(hmac.new(b"test-secret", body, hashlib.sha256).digest()).decode()
    assert line.verify_signature(body, sig, "test-secret")
    assert not line.verify_signature(body, "bad", "test-secret")
    assert not line.verify_signature(body, sig, "")


def test_line_commands(svc):
    assert "メニュー" in line.respond(svc, "U1", "こんにちは")[0]
    assert "誕生日を添えて" in line.respond(svc, "U1", "星座")[0]
    assert "おひつじ座" in line.respond(svc, "U1", "星座 3/21")[0]
    assert "おひつじ座" in line.respond(svc, "U1", "星座")[0]  # 登録済みの誕生日を使う
    first = line.respond(svc, "U1", "タロット")
    assert "】今日のあなた:" in first[0] and "鑑定文です" in first[1]
    assert "終わりました" in line.respond(svc, "U1", "タロット")[0]
    replies = line.respond(svc, "U1", "3枚")
    assert "プレミアム" in replies[0] and len(replies) == 2


# --- Web API --------------------------------------------------------------
def test_web_api():
    from fastapi.testclient import TestClient

    from app import main
    main.service.client = FakeClient()
    c = TestClient(main.app)
    assert c.get("/").status_code == 200
    assert c.get("/api/me").json()["limit"] == 1
    assert len(c.get("/api/me").json()["rarities"]) == 5
    d = c.post("/api/tarot/draw", json={"count": 1}).json()
    assert d["ok"] and len(d["cards"]) == 1 and "rarity" in d["cards"][0]
    r = c.post("/api/tarot/read", json={"draw_id": d["draw_id"]}).json()
    assert r["ok"] and "鑑定文です" in r["text"]
    assert c.post("/api/tarot/read", json={"draw_id": "nope"}).status_code == 404
    assert c.post("/api/tarot/draw", json={"count": 1}).json()["reason"] == "limit"
    assert c.post("/api/tarot/draw", json={"count": 2}).status_code == 400
    assert c.post("/api/horoscope", json={"birthday": "8/1"}).json()["sign"] == "しし座"
    assert c.post("/api/horoscope", json={"birthday": "abc"}).status_code == 400
    assert c.post("/line/callback", content=b"{}", headers={"x-line-signature": "x"}).status_code == 400
    assert c.post("/billing/checkout").status_code == 503
