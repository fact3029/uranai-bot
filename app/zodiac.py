"""星座の判定と、その日の運勢の元データ（順位・ラッキー情報）。

同じ日・同じ星座なら誰が見ても同じ結果になるよう、日付から決まる乱数で作る。
"""
import hashlib
import random
import re
from datetime import date

# (星座名, 開始月, 開始日) 開始日の早い順
SIGNS = [
    ("やぎ座", 12, 22), ("みずがめ座", 1, 20), ("うお座", 2, 19), ("おひつじ座", 3, 21),
    ("おうし座", 4, 20), ("ふたご座", 5, 21), ("かに座", 6, 22), ("しし座", 7, 23),
    ("おとめ座", 8, 23), ("てんびん座", 9, 23), ("さそり座", 10, 24), ("いて座", 11, 23),
]
SIGN_NAMES = [s[0] for s in SIGNS]

COLORS = ["赤", "オレンジ", "黄色", "黄緑", "緑", "水色", "青", "紫", "ピンク", "白", "黒", "金", "銀", "ベージュ"]
ITEMS = ["ハンカチ", "手帳", "温かい飲み物", "イヤホン", "鍵", "花", "本", "腕時計", "リップ", "小銭入れ", "観葉植物", "香り"]


def sign_of(month: int, day: int) -> str:
    date(2000, month, day)  # 存在しない日付なら ValueError
    if (month, day) >= (12, 22):
        return "やぎ座"
    for name, m, d in reversed(SIGNS[1:]):
        if (month, day) >= (m, d):
            return name
    return "やぎ座"  # 1/1〜1/19 と 12/22〜12/31


def parse_birthday(text: str) -> tuple[int, int] | None:
    """「1990-03-21」「3/21」「3月21日」などから(月, 日)を取り出す。"""
    m = re.search(r"(?:(\d{4})[-/年.])?\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", text)
    if not m:
        return None
    month, day = int(m.group(2)), int(m.group(3))
    try:
        date(2000, month, day)
    except ValueError:
        return None
    return month, day


def daily_ranking(day: date) -> list[str]:
    seed = int(hashlib.sha256(f"rank:{day.isoformat()}".encode()).hexdigest(), 16)
    names = SIGN_NAMES[:]
    random.Random(seed).shuffle(names)
    return names


def daily_fortune(sign: str, day: date) -> dict:
    if sign not in SIGN_NAMES:
        raise ValueError(f"unknown sign: {sign}")
    seed = int(hashlib.sha256(f"{sign}:{day.isoformat()}".encode()).hexdigest(), 16)
    rng = random.Random(seed)
    return {
        "sign": sign,
        "date": day.isoformat(),
        "rank": daily_ranking(day).index(sign) + 1,
        "lucky_color": rng.choice(COLORS),
        "lucky_item": rng.choice(ITEMS),
        "scores": {k: rng.randint(1, 5) for k in ("総合", "恋愛", "仕事", "金運")},
    }
