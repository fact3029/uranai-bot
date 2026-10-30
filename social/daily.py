"""毎朝の自動投稿。

    python -m social.daily --dry-run          # 画像・動画・投稿文を out/ に作るだけ（投稿しない）
    python -m social.daily                    # 設定済みのSNSすべてに投稿
    python -m social.daily --only x,threads   # 一部だけ投稿（失敗したSNSのやり直しなど）

設定が無いSNSは飛ばす。1つ失敗しても他は続け、最後に失敗があれば終了コード1を返す。
"""
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import httpx

from app.service import today_jst

from . import content, posters, render, storage
from .config import PLATFORMS, SocialSettings

log = logging.getLogger("social.daily")


def run(day: date, out: Path, only: list[str], dry_run: bool, s: SocialSettings | None = None,
        http: httpx.Client | None = None, claude=None) -> dict:
    s = s or SocialSettings()
    out.mkdir(parents=True, exist_ok=True)
    c = content.build(day, client=claude)
    files = {
        "ranking": render.ranking_image(c, out / "ranking.jpg"),
        "card": render.card_image(c, out / "card.jpg"),
        "video": render.gacha_video(c, out / "gacha.mp4"),
    }
    texts = {
        "x": content.caption_x(c),
        "long": content.caption_long(c),
        "video_title": content.video_title(c),
    }
    summary = {"date": day.isoformat(), "card": c.card.label, "rarity": c.card.rarity, "texts": texts, "results": {}}
    (out / "captions.txt").write_text(
        f"--- X ---\n{texts['x']}\n\n--- Threads / Instagram / LINE / TikTok ---\n{texts['long']}\n\n"
        f"--- 動画タイトル ---\n{texts['video_title']}\n", encoding="utf-8")

    targets = [p for p in PLATFORMS if (not only or p in only)]
    if dry_run:
        summary["results"] = {p: "dry-run" for p in targets}
        _save(out, summary)
        return summary

    if "line" in targets and str(day.weekday()) not in s.line_broadcast_weekdays.split(","):
        summary["results"]["line"] = "skip: 配信する曜日ではない"
        targets.remove("line")
    for p in list(targets):
        if not s.ready(p):
            summary["results"][p] = "skip: 設定なし"
            targets.remove(p)

    urls = {}
    if any(p in targets for p in ("threads", "instagram", "line")):
        prefix = f"daily/{day.isoformat()}"
        try:
            urls = {k: storage.upload(s, f, f"{prefix}/{f.name}") for k, f in files.items()}
        except Exception as e:  # 置き場に上げられないとURLが必要なSNSは全部できない
            log.exception("メディアのアップロードに失敗")
            for p in ("threads", "instagram", "line"):
                if p in targets:
                    summary["results"][p] = f"error: アップロード失敗 {e}"
                    targets.remove(p)

    own_http = http is None
    http = http or httpx.Client(timeout=60)
    jobs = {
        "x": lambda: posters.post_x(s, texts["x"], [files["ranking"], files["card"]], http),
        "threads": lambda: posters.post_threads(s, texts["long"], [urls["ranking"], urls["card"]], http),
        "instagram": lambda: {
            "carousel": posters.post_instagram_carousel(s, texts["long"], [urls["ranking"], urls["card"]], http),
            "reel": posters.post_instagram_reel(s, texts["long"], urls["video"], http),
        },
        "youtube": lambda: posters.post_youtube(s, texts["video_title"], texts["long"], files["video"]),
        "line": lambda: posters.post_line_broadcast(s, texts["long"], urls["ranking"], http),
    }
    try:
        for p in targets:
            try:
                summary["results"][p] = {"ok": jobs[p]()}
                log.info("%s に投稿しました", p)
            except Exception as e:
                log.exception("%s への投稿に失敗", p)
                summary["results"][p] = f"error: {e}"
    finally:
        if own_http:
            http.close()
    _save(out, summary)
    return summary


def _save(out: Path, summary: dict) -> None:
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="毎朝の占い自動投稿")
    ap.add_argument("--date", help="YYYY-MM-DD（省略時は日本時間の今日）")
    ap.add_argument("--only", default="", help="投稿先をカンマ区切りで指定: " + ",".join(PLATFORMS))
    ap.add_argument("--out", default="out")
    ap.add_argument("--dry-run", action="store_true", help="作るだけで投稿しない")
    a = ap.parse_args(argv)
    only = [p.strip() for p in a.only.split(",") if p.strip()]
    bad = [p for p in only if p not in PLATFORMS]
    if bad:
        ap.error(f"不明な投稿先: {bad}")
    day = date.fromisoformat(a.date) if a.date else today_jst()
    summary = run(day, Path(a.out), only, a.dry_run)
    print(json.dumps(summary["results"], ensure_ascii=False, indent=2, default=str))
    return 1 if any(str(v).startswith("error") for v in summary["results"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
