import json
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace

os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["DB_PATH"] = ":memory:"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app import zodiac  # noqa: E402
from social import content, daily, posters, render  # noqa: E402
from social.config import SocialSettings  # noqa: E402

DAY = date(2026, 10, 30)


class FakeClaude:
    def __init__(self, payload):
        text = json.dumps(payload, ensure_ascii=False)
        resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: self.calls.append(k) or resp))


def test_content_is_stable_and_matches_line_bot():
    a, b = content.build(DAY), content.build(DAY)
    assert [f["sign"] for f in a.ranking] == zodiac.daily_ranking(DAY)
    assert a.card == b.card


def test_content_uses_claude_and_clips():
    fake = FakeClaude({"card_message": "あ" * 80, "top_comment": "最高の日", "last_comment": "休もう"})
    c = content.build(DAY, client=fake)
    assert len(c.card_message) == 40 and c.card_message.endswith("…")
    assert c.hooks["top"] == "最高の日"
    req = fake.calls[0]
    assert req["output_config"]["format"]["type"] == "json_schema" and req["fallbacks"] == "default"


def test_captions_fit_limits():
    c = content.build(DAY)
    assert content.x_weight(content.caption_x(c)) <= 280
    long = content.caption_long(c)
    assert len(long) <= 500 and c.ranking[0]["sign"] in long and "娯楽" in long
    assert c.card.rarity not in content.video_title(c)  # 動画のネタバレをしない


def test_images_render(tmp_path):
    c = content.build(DAY)
    for fn, name in ((render.ranking_image, "r.jpg"), (render.card_image, "c.jpg")):
        p = fn(c, tmp_path / name)
        from PIL import Image
        assert Image.open(p).size == (1080, 1350)


def test_video_first_frame_size():
    assert next(render.gacha_frames(content.build(DAY))).size == (1080, 1920)


# --- 投稿（偽の通信）--------------------------------------------------------
def settings(**kw):
    base = dict(x_api_key="k", x_api_secret="s", x_access_token="t", x_access_secret="ts",
                threads_user_id="TU", threads_token="TT", ig_user_id="IU", ig_token="IT",
                s3_bucket="b", s3_key_id="i", s3_secret="x", media_base_url="https://media.example.com",
                line_token="LT", line_broadcast_weekdays="4")
    base.update(kw)
    return SocialSettings(**base)


def recorder(handler):
    seen = []

    def h(req: httpx.Request):
        seen.append(req)
        return handler(req)
    return httpx.Client(transport=httpx.MockTransport(h)), seen


def test_post_x(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"jpg")
    n = iter(range(100))

    def h(req):
        if req.url.path == "/2/media/upload":
            return httpx.Response(200, json={"data": {"id": f"m{next(n)}"}})
        return httpx.Response(201, json={"data": {"id": "tw1"}})
    http, seen = recorder(h)
    assert posters.post_x(settings(), "hello", [img, img], http) == "tw1"
    assert [r.url.path for r in seen] == ["/2/media/upload", "/2/media/upload", "/2/tweets"]
    assert all(r.headers["authorization"].startswith("OAuth ") for r in seen)
    assert json.loads(seen[-1].content)["media"]["media_ids"] == ["m0", "m1"]


def test_post_threads_carousel(monkeypatch):
    monkeypatch.setattr(posters.time, "sleep", lambda s: None)
    ids = iter(["c1", "c2", "car", "pub"])
    http, seen = recorder(lambda req: httpx.Response(200, json={"id": next(ids)}))
    assert posters.post_threads(settings(), "text", ["https://m/1.jpg", "https://m/2.jpg"], http) == "pub"
    car = seen[2].url.params
    assert car["media_type"] == "CAROUSEL" and car["children"] == "c1,c2"
    assert seen[3].url.path.endswith("/threads_publish") and seen[3].url.params["creation_id"] == "car"


def test_post_instagram_waits_for_finished(monkeypatch):
    monkeypatch.setattr(posters.time, "sleep", lambda s: None)
    states = iter(["IN_PROGRESS", "FINISHED"])
    ids = iter(["c1", "c2", "car"])

    def h(req):
        if req.method == "GET":
            return httpx.Response(200, json={"status_code": next(states)})
        if req.url.path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "post1"})
        return httpx.Response(200, json={"id": next(ids)})
    http, seen = recorder(h)
    assert posters.post_instagram_carousel(settings(), "cap", ["https://m/1.jpg", "https://m/2.jpg"], http) == "post1"
    assert sum(r.method == "GET" for r in seen) == 2


def test_instagram_error_status(monkeypatch):
    monkeypatch.setattr(posters.time, "sleep", lambda s: None)

    def h(req):
        return httpx.Response(200, json={"status_code": "ERROR"} if req.method == "GET" else {"id": "x"})
    http, _ = recorder(h)
    with pytest.raises(posters.PostError):
        posters.post_instagram_reel(settings(), "cap", "https://m/v.mp4", http)


def test_x_error_is_reported():
    http, _ = recorder(lambda req: httpx.Response(402, json={"title": "CreditsDepleted"}))
    with pytest.raises(posters.PostError, match="402"):
        posters.post_x(settings(), "hi", [], http)


# --- 全体の流れ --------------------------------------------------------------
@pytest.fixture
def fast_video(monkeypatch):
    monkeypatch.setattr(render, "gacha_video", lambda c, p: (p.write_bytes(b"mp4"), p)[1])


def test_dry_run_writes_files(tmp_path, fast_video):
    summary = daily.run(DAY, tmp_path, [], dry_run=True)
    assert {p.name for p in tmp_path.iterdir()} >= {"ranking.jpg", "card.jpg", "gacha.mp4", "captions.txt", "summary.json"}
    assert set(summary["results"].values()) == {"dry-run"}


def test_run_posts_and_continues_after_failure(tmp_path, fast_video, monkeypatch):
    monkeypatch.setattr(posters.time, "sleep", lambda s: None)
    monkeypatch.setattr(daily.storage, "upload", lambda s, f, key: f"https://media.example.com/{key}")
    ids = iter(range(1000))

    def h(req):
        host = req.url.host
        if host == "api.x.com":
            return httpx.Response(500, text="boom")  # X だけ失敗させる
        if req.method == "GET":
            return httpx.Response(200, json={"status_code": "FINISHED"})
        return httpx.Response(200, json={"id": f"id{next(ids)}"})
    http, seen = recorder(h)
    s = settings()  # YouTube は未設定 → 飛ばす。DAY は金曜(4)なので LINE は配信する
    summary = daily.run(DAY, tmp_path, [], dry_run=False, s=s, http=http)
    r = summary["results"]
    assert r["x"].startswith("error")
    assert "ok" in r["threads"] and "ok" in r["instagram"] and "ok" in r["line"]
    assert r["youtube"] == "skip: 設定なし"
    line_req = [q for q in seen if q.url.host == "api.line.me"][0]
    assert json.loads(line_req.content)["messages"][0]["originalContentUrl"].endswith("/ranking.jpg")


def test_line_only_on_configured_weekdays(tmp_path, fast_video):
    s = settings(line_broadcast_weekdays="0")
    summary = daily.run(DAY, tmp_path, ["line"], dry_run=False, s=s, http=httpx.Client())
    assert summary["results"]["line"].startswith("skip")


def test_cli_rejects_unknown_platform():
    with pytest.raises(SystemExit):
        daily.main(["--only", "tiktok", "--dry-run"])
