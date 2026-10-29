"""LINE と Web で共通の占い処理。回数制限と有料機能の判定もここで行う。

Web では「カードを引く（すぐ返る）」と「鑑定文を読む（AIを待つ）」を分け、
ガチャ演出の間にAIの文章を用意する。
"""
import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import reader, tarot, zodiac
from .config import settings
from .store import Store

JST = timezone(timedelta(hours=9))


def today_jst() -> date:
    return datetime.now(JST).date()


@dataclass
class Result:
    ok: bool
    text: str
    reason: str = ""  # "limit" | "premium_only" | "not_found" | ""
    cards: list = field(default_factory=list)
    draw_id: str = ""


def _card_dict(c: tarot.DrawnCard) -> dict:
    return asdict(c) | {"label": c.label}


class FortuneService:
    def __init__(self, store: Store, client=None):
        self.store = store
        self.client = client  # テスト用。None なら reader が設定から作る

    def daily_limit(self, user_id: str) -> int:
        return settings.premium_daily_limit if self.store.is_premium(user_id) else settings.free_daily_limit

    def draw(self, user_id: str, count: int = 1, question: str = "") -> Result:
        """カードを引いて保存する。回数はここで1回分使う。AIは呼ばない。"""
        premium = self.store.is_premium(user_id)
        if (count == 3 or question.strip()) and not premium:
            return Result(False, "3枚引き・相談つきの鑑定はプレミアム会員向けです。", "premium_only")
        if not self.store.try_consume(user_id, today_jst(), self.daily_limit(user_id)):
            msg = "今日の鑑定回数は終わりました。また明日お越しください。"
            if not premium:
                msg += "\nプレミアム会員なら1日に何度でも（上限あり）占えます。"
            return Result(False, msg, "limit")
        cards = tarot.draw(count)
        draw_id = secrets.token_urlsafe(12)
        dicts = [_card_dict(c) for c in cards]
        self.store.save_draw(draw_id, user_id, json.dumps(dicts, ensure_ascii=False), question.strip()[:500])
        return Result(True, "", cards=dicts, draw_id=draw_id)

    def read(self, user_id: str, draw_id: str) -> Result:
        """引いたカードの鑑定文を返す。一度作った文は保存して使い回す。"""
        row = self.store.get_draw(draw_id, user_id)
        if row is None:
            return Result(False, "鑑定が見つかりません。", "not_found")
        cards_json, question, text = row
        dicts = json.loads(cards_json)
        if text is None:
            cards = [tarot.DrawnCard(**{k: v for k, v in d.items() if k != "label"}) for d in dicts]
            text = reader.tarot_reading(cards, question, client=self.client)
            self.store.save_reading(draw_id, text)
        return Result(True, text, cards=dicts, draw_id=draw_id)

    def tarot(self, user_id: str, count: int = 1, question: str = "") -> Result:
        """引いてすぐ読む（LINE 用）。"""
        r = self.draw(user_id, count, question)
        return self.read(user_id, r.draw_id) if r.ok else r

    def horoscope(self, month: int, day: int) -> Result:
        """星座占いは無料・回数無制限。1日12星座分だけAIを呼び、結果を使い回す。"""
        sign = zodiac.sign_of(month, day)
        today = today_jst()
        fortune = zodiac.daily_fortune(sign, today)
        body = self.store.cached_horoscope(sign, today)
        if body is None:
            body = reader.horoscope_reading(fortune, client=self.client)
            self.store.save_horoscope(sign, today, body)
        s = fortune["scores"]
        header = (
            f"🌙 {today.month}月{today.day}日の{sign}  第{fortune['rank']}位\n"
            f"総合 {reader.stars(s['総合'])}\n恋愛 {reader.stars(s['恋愛'])}\n"
            f"仕事 {reader.stars(s['仕事'])}\n金運 {reader.stars(s['金運'])}\n"
            f"ラッキーカラー: {fortune['lucky_color']} / アイテム: {fortune['lucky_item']}"
        )
        return Result(True, f"{header}\n\n{body}")
