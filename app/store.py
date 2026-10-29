"""SQLite に利用回数・有料会員・誕生日・その日の星座占い文を保存する。"""
import sqlite3
import threading
from datetime import date

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (user_id TEXT, day TEXT, count INTEGER, PRIMARY KEY (user_id, day));
CREATE TABLE IF NOT EXISTS members (user_id TEXT PRIMARY KEY, subscription_id TEXT, active INTEGER);
CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, month INTEGER, day INTEGER);
CREATE TABLE IF NOT EXISTS draws (id TEXT PRIMARY KEY, user_id TEXT, cards TEXT, question TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS horoscope_cache (sign TEXT, day TEXT, text TEXT, PRIMARY KEY (sign, day));
"""


class Store:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def _q(self, sql: str, args: tuple = ()):
        with self._lock, self._conn:
            return self._conn.execute(sql, args).fetchall()

    # 利用回数 -------------------------------------------------------------
    def used_today(self, user_id: str, today: date) -> int:
        rows = self._q("SELECT count FROM usage WHERE user_id=? AND day=?", (user_id, today.isoformat()))
        return rows[0][0] if rows else 0

    def try_consume(self, user_id: str, today: date, limit: int) -> bool:
        """上限内なら1回分を記録して True。上限なら False。"""
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT count FROM usage WHERE user_id=? AND day=?", (user_id, today.isoformat())
            ).fetchone()
            used = row[0] if row else 0
            if used >= limit:
                return False
            self._conn.execute(
                "INSERT INTO usage VALUES (?,?,1) ON CONFLICT(user_id, day) DO UPDATE SET count=count+1",
                (user_id, today.isoformat()),
            )
            return True

    def refund(self, user_id: str, today: date) -> None:
        """占いの生成に失敗した時に回数を戻す。"""
        self._q("UPDATE usage SET count=MAX(count-1,0) WHERE user_id=? AND day=?", (user_id, today.isoformat()))

    # 有料会員 -------------------------------------------------------------
    def is_premium(self, user_id: str) -> bool:
        rows = self._q("SELECT active FROM members WHERE user_id=?", (user_id,))
        return bool(rows and rows[0][0])

    def set_premium(self, user_id: str, subscription_id: str, active: bool) -> None:
        self._q(
            "INSERT INTO members VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "subscription_id=excluded.subscription_id, active=excluded.active",
            (user_id, subscription_id, int(active)),
        )

    def deactivate_subscription(self, subscription_id: str) -> None:
        self._q("UPDATE members SET active=0 WHERE subscription_id=?", (subscription_id,))

    # 誕生日 ---------------------------------------------------------------
    def set_birthday(self, user_id: str, month: int, day: int) -> None:
        self._q(
            "INSERT INTO profiles VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET month=excluded.month, day=excluded.day",
            (user_id, month, day),
        )

    def birthday(self, user_id: str) -> tuple[int, int] | None:
        rows = self._q("SELECT month, day FROM profiles WHERE user_id=?", (user_id,))
        return (rows[0][0], rows[0][1]) if rows else None

    # 引いたカード（引く→読むを分けるため保存する）------------------------
    def save_draw(self, draw_id: str, user_id: str, cards_json: str, question: str) -> None:
        self._q("INSERT INTO draws VALUES (?,?,?,?,NULL)", (draw_id, user_id, cards_json, question))

    def get_draw(self, draw_id: str, user_id: str) -> tuple[str, str, str | None] | None:
        """本人の引いた結果だけ返す: (cards_json, question, text)"""
        rows = self._q("SELECT cards, question, text FROM draws WHERE id=? AND user_id=?", (draw_id, user_id))
        return rows[0] if rows else None

    def save_reading(self, draw_id: str, text: str) -> None:
        self._q("UPDATE draws SET text=? WHERE id=?", (text, draw_id))

    # 星座占い文のキャッシュ（1日12星座×1回だけAIを呼ぶ）-----------------
    def cached_horoscope(self, sign: str, today: date) -> str | None:
        rows = self._q("SELECT text FROM horoscope_cache WHERE sign=? AND day=?", (sign, today.isoformat()))
        return rows[0][0] if rows else None

    def save_horoscope(self, sign: str, today: date, text: str) -> None:
        self._q("INSERT OR REPLACE INTO horoscope_cache VALUES (?,?,?)", (sign, today.isoformat(), text))
