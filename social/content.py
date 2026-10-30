"""毎日の投稿の中身（12星座ランキング・みんなの今日の1枚・投稿文）を作る。

数字やカードはプログラムで決め、AIには短い一言だけ書かせる。
同じ日なら何度実行しても同じランキングとカードになる（LINE bot の星座占いとも一致）。
"""
import hashlib
import json
import logging
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import date

import anthropic

from app import tarot, zodiac
from app.config import settings
from app.reader import SYSTEM_PROMPT

log = logging.getLogger(__name__)
WEEKDAYS = "月火水木金土日"
HASHTAGS = ["#占い", "#星座占い", "#タロット", "#今日の運勢"]


@dataclass
class DailyContent:
    day: date
    ranking: list[dict]          # 1位から順に zodiac.daily_fortune の結果
    card: tarot.DrawnCard        # みんなの今日の1枚
    card_message: str            # カードの一言（画像・動画に載せる）
    hooks: dict = field(default_factory=dict)  # 1位・12位への一言など

    @property
    def date_label(self) -> str:
        return f"{self.day.month}/{self.day.day}（{WEEKDAYS[self.day.weekday()]}）"


def card_of_the_day(day: date) -> tarot.DrawnCard:
    seed = int(hashlib.sha256(f"card:{day.isoformat()}".encode()).hexdigest(), 16)
    return tarot.draw(1, random.Random(seed))[0]


def _ask_claude(prompt: str, client) -> dict | None:
    if client is None:
        return None
    schema = {
        "type": "object",
        "properties": {
            "card_message": {"type": "string", "description": "今日の1枚から全員へのメッセージ。40字以内"},
            "top_comment": {"type": "string", "description": "1位の星座への一言。25字以内"},
            "last_comment": {"type": "string", "description": "12位の星座への励まし。25字以内"},
        },
        "required": ["card_message", "top_comment", "last_comment"],
        "additionalProperties": False,
    }
    try:
        resp = client.beta.messages.create(
            model=settings.claude_model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError:
        log.exception("Claude API エラー（定型文を使います）")
        return None
    if resp.stop_reason != "end_turn":
        log.warning("Claude の応答が完了していません: %s", resp.stop_reason)
        return None
    try:
        return json.loads("".join(b.text for b in resp.content if b.type == "text"))
    except (json.JSONDecodeError, TypeError):
        log.warning("Claude の応答がJSONではありません")
        return None


def build(day: date, client=None) -> DailyContent:
    ranking = [zodiac.daily_fortune(s, day) for s in zodiac.daily_ranking(day)]
    card = card_of_the_day(day)
    if client is None and settings.anthropic_api_key:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    prompt = (
        f"SNSに投稿する{day.month}月{day.day}日の占いの短い文を作ってください。\n"
        f"今日の1枚: {card.label}（意味: {card.meaning}）\n"
        f"1位: {ranking[0]['sign']}、12位: {ranking[-1]['sign']}\n"
        "どれも短く、スマホで一瞬で読めるように。絵文字は1つまで。"
    )
    got = _ask_claude(prompt, client) or {}
    first_kw = card.meaning.split("・")[0]
    return DailyContent(
        day=day,
        ranking=ranking,
        card=card,
        card_message=_clip(got.get("card_message") or f"今日のキーワードは「{first_kw}」。", 40),
        hooks={
            "top": _clip(got.get("top_comment") or "流れに乗れる日。思い切って動いてみて", 25),
            "last": _clip(got.get("last_comment") or "ひと休みが開運のカギ。自分をいたわって", 25),
        },
    )


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


# --- 投稿文 -----------------------------------------------------------------
def x_weight(text: str) -> int:
    """X の文字数の数え方（全角などは2、半角は1）の近似。上限は280。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WFA" or ord(ch) > 0xFFFF else 1 for ch in text)


def caption_x(c: DailyContent) -> str:
    lines = [f"🌙{c.date_label} 12星座ランキング", f"👑1位 {c.ranking[0]['sign']}　{c.hooks['top']}"]
    lines += [f"{i}位 {f['sign']}" for i, f in enumerate(c.ranking[1:3], start=2)]
    lines += [f"🔮今日の1枚 {c.card.label}【{c.card.rarity}】", "", " ".join(HASHTAGS[:3])]
    text = "\n".join(lines)
    while x_weight(text) > 280 and len(lines) > 4:  # 長すぎる時は2位・3位から削る
        lines.pop(2)
        text = "\n".join(lines)
    return text


def caption_long(c: DailyContent, limit: int = 500) -> str:
    """Threads（500字）・Instagram・LINE 向けの長めの文。"""
    rows = [f"{i}位 {f['sign']}" + ("👑" if i == 1 else "") for i, f in enumerate(c.ranking, start=1)]
    parts = [
        f"🌙{c.date_label}の12星座ランキング",
        "\n".join(rows),
        f"1位の{c.ranking[0]['sign']}さん：{c.hooks['top']}",
        f"12位の{c.ranking[-1]['sign']}さん：{c.hooks['last']}",
        f"🔮みんなの今日の1枚は「{c.card.label}」【{c.card.rarity}】\n{c.card_message}",
        "※占いは娯楽です",
        " ".join(HASHTAGS),
    ]
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def video_title(c: DailyContent) -> str:
    return f"{c.date_label} 今日の運命のカードは…？ #Shorts #タロット #占い"
