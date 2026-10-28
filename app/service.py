"""LINE と Web で共通の占い処理。回数制限と有料機能の判定もここで行う。"""
from dataclasses import dataclass, field
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
    reason: str = ""  # "limit" | "premium_only" | ""
    cards: list = field(default_factory=list)


class FortuneService:
    def __init__(self, store: Store, client=None):
        self.store = store
        self.client = client  # テスト用。None なら reader が設定から作る

    def daily_limit(self, user_id: str) -> int:
        return settings.premium_daily_limit if self.store.is_premium(user_id) else settings.free_daily_limit

    def tarot(self, user_id: str, count: int = 1, question: str = "") -> Result:
        premium = self.store.is_premium(user_id)
        if (count == 3 or question.strip()) and not premium:
            return Result(False, "3枚引き・相談つきの鑑定はプレミアム会員向けです。", "premium_only")
        today = today_jst()
        if not self.store.try_consume(user_id, today, self.daily_limit(user_id)):
            msg = "今日の鑑定回数は終わりました。また明日お越しください。"
            if not premium:
                msg += "\nプレミアム会員なら1日に何度でも（上限あり）占えます。"
            return Result(False, msg, "limit")
        try:
            cards = tarot.draw(count)
            text = reader.tarot_reading(cards, question, client=self.client)
        except Exception:
            self.store.refund(user_id, today)
            raise
        return Result(True, text, cards=[c.__dict__ | {"label": c.label} for c in cards])

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
