import json
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from farmstudio import core
from farmstudio.app import create_app
from farmstudio.core import Studio, fingerprint
from farmstudio.media import render, validate_segments

HEADERS = {"X-Local-Action": "1"}
CHECKS = {key: True for key in ("identity", "voice", "subtitles", "rights", "ai_label", "watched")}


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch):
    monkeypatch.setattr(core, "today", lambda: "2026-11-16")


def reserve(studio, pid, attempt=None):
    return studio.reserve(pid, attempt or str(uuid.uuid4()), 15, core.MODEL, 10, "720p", 1)


def test_three_unique_per_day_and_idempotence(tmp_path):
    studio = Studio(tmp_path)
    first = studio.generate("2026-11-16")
    assert [p["id"] for p in first] == [p["id"] for p in studio.generate("2026-11-16")]
    ids = set()
    for n in range(7):
        docs = studio.generate((date(2026, 11, 16)+timedelta(days=n)).isoformat())
        assert len(docs) == 3
        for doc in docs:
            assert doc["idea_id"] not in ids
            ids.add(doc["idea_id"])
            assert "boné bege" in doc["prompt"]
    assert len(ids) == 21
    with pytest.raises(ValueError, match="esgotado"):
        studio.generate("2026-11-23")


def test_concurrent_daily_generation_is_single_batch(tmp_path):
    studio = Studio(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: studio.generate(), range(4)))
    assert all([d["id"] for d in batch] == [d["id"] for d in results[0]] for batch in results)
    assert len(studio.list()) == 3


def test_credit_limit_atomic_and_idempotent(tmp_path):
    studio = Studio(tmp_path)
    pid = studio.generate()[0]["id"]
    attempt = str(uuid.uuid4())
    reserve(studio, pid, attempt)
    reserve(studio, pid, attempt)
    assert studio.budget()["used_or_reserved"] == 15
    def try_reserve(_):
        try:
            reserve(studio, pid)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=5) as pool:
        assert sum(pool.map(try_reserve, range(5))) == 2
    assert studio.budget()["used_or_reserved"] == 45


def test_uncertain_charge_counts_until_confirmed_refund(tmp_path):
    studio = Studio(tmp_path)
    pid = studio.generate()[0]["id"]
    attempt = str(uuid.uuid4())
    reserve(studio, pid, attempt)
    studio.credit_state(attempt, "uncertain")
    assert studio.budget()["remaining"] == 30
    studio.credit_state(attempt, "refunded")
    assert studio.budget()["remaining"] == 45


def test_changed_price_and_retirement_fail_closed(tmp_path, monkeypatch):
    studio = Studio(tmp_path)
    pid = studio.generate()[0]["id"]
    with pytest.raises(ValueError, match="divergente"):
        studio.reserve(pid, str(uuid.uuid4()), 30, core.MODEL, 10, "720p", 1)
    monkeypatch.setattr(core, "today", lambda: "2026-12-05")
    with pytest.raises(ValueError, match="aposentado"):
        reserve(studio, pid)


@pytest.mark.parametrize("segments", [[], [{"start": 2, "end": 1, "text": "A"}], [{"start": 0, "end": 11, "text": "A"}], [{"start": 0, "end": 2, "text": "A"}, {"start": 1, "end": 3, "text": "B"}], [{"start": float("nan"), "end": 2, "text": "A"}], [{"start": 0}]])
def test_bad_captions_rejected(segments):
    with pytest.raises(ValueError):
        validate_segments(segments)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, schedule=False)) as c:
        yield c


def test_api_local_security_and_approval_gate(client):
    assert client.get("/").status_code == 200
    assert client.post("/api/daily").status_code == 403
    assert client.post("/api/daily", headers={**HEADERS, "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 400
    docs = client.post("/api/daily", headers=HEADERS).json()
    pid = docs[0]["id"]
    assert client.post(f"/api/productions/{pid}/approve", headers=HEADERS, json=CHECKS).status_code == 400
    assert client.post(f"/api/productions/{pid}/publication", headers=HEADERS, json={"url": "https://www.tiktok.com/@test/video/1"}).status_code == 400
    assert client.post(f"/api/productions/{pid}/process/transcribe", headers=HEADERS).status_code == 400


def test_render_and_stale_approval_with_actual_ffmpeg(tmp_path):
    studio = Studio(tmp_path)
    doc = studio.generate()[0]
    folder = studio.folder(doc)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=180x320:rate=24:duration=10", "-f", "lavfi", "-i", "sine=frequency=220:duration=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(folder/"source.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=700:duration=0.3", str(folder/"sfx.wav")], check=True)
    doc["source"] = {"file": "source.mp4"}
    doc["sfx"] = {"file": "sfx.wav", "sha256": fingerprint(folder/"sfx.wav"), "rights": "efeito sintetizado para teste", "license": "original"}
    doc["transcript"] = {"reviewed": True, "segments": [{"start": .5, "end": 3, "text": "Café e prosa."}]}
    doc["render"] = render(studio, doc, width=180, height=320)
    assert (folder/"final.mp4").stat().st_size > 1000
    assert "GERADOS POR IA" in (folder/"captions.ass").read_text()
    doc["status"] = "pronto"
    with studio.connect() as con:
        studio._save(con, doc)
    approved = studio.approve(doc["id"], CHECKS)
    assert approved["status"] == "aprovado"
    with (folder/"final.mp4").open("ab") as f:
        f.write(b"modified")
    with pytest.raises(ValueError, match="mudou"):
        studio.published(doc["id"], "https://www.tiktok.com/@test/video/1")


def test_metrics_snapshots_not_double_counted_and_csv_atomic(client):
    studio = client.app.state.studio
    doc = studio.generate()[0]
    doc["status"] = "publicado"
    with studio.connect() as con:
        studio._save(con, doc)
    pid = doc["id"]
    metric = {"measured_at": "2026-11-16T12:00:00-03:00", "views": 1000, "followers": 10, "likes": 100, "comments": 3, "shares": 8, "average_watch_seconds": 7.3, "completion_rate": 60}
    assert client.post(f"/api/productions/{pid}/metrics", headers=HEADERS, json=metric).status_code == 200
    metric.update(measured_at="2026-11-16T14:00:00-03:00", views=1500)
    assert client.post(f"/api/productions/{pid}/metrics", headers=HEADERS, json=metric).status_code == 200
    assert client.get("/api/feedback").json()["ranking"][0]["views"] == 1500
    metric["completion_rate"] = 120
    assert client.post(f"/api/productions/{pid}/metrics", headers=HEADERS, json=metric).status_code == 422
    body = "production_id,measured_at,views,followers,likes,comments,shares,average_watch_seconds,completion_rate\n"+f"{pid},2026-11-16T16:00:00-03:00,2000,12,130,4,10,7.5,70\n"+"bad-id,2026-11-16T16:00:00-03:00,2000,12,130,4,10,7.5,70\n"
    assert client.post("/api/metrics/import", headers=HEADERS, files={"file": ("metrics.csv", body, "text/csv")}).status_code == 400
    assert client.get("/api/feedback").json()["ranking"][0]["views"] == 1500
