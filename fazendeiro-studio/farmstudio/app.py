from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import PACKAGE, Studio, fingerprint, now, today, ZONE
from .media import probe, render, transcribe, validate_segments, validate_source


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Reservation(Input):
    attempt: uuid.UUID
    confirmed_cost: int
    model: str
    duration: int
    resolution: str
    generations: int


class Transcript(Input):
    segments: list[dict] = Field(min_length=1, max_length=100)


class Approval(Input):
    identity: bool
    voice: bool
    subtitles: bool
    rights: bool
    ai_label: bool
    watched: bool


class Publication(Input):
    url: str = Field(max_length=1000)


class Metric(Input):
    measured_at: datetime
    views: int = Field(ge=0, le=10**12)
    followers: int = Field(ge=0, le=10**10)
    likes: int = Field(ge=0, le=10**12)
    comments: int = Field(ge=0, le=10**12)
    shares: int = Field(ge=0, le=10**12)
    average_watch_seconds: float = Field(ge=0, le=600)
    completion_rate: float = Field(ge=0, le=100)


class Followers(Input):
    current_followers: int = Field(ge=0, le=10**10)


def create_app(root=None, schedule=True):
    studio = Studio(root)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="studio-media")

    def work(pid, operation):
        try:
            doc = studio.get(pid)
            result = transcribe(studio, doc) if operation == "transcribe" else render(studio, doc)
            with studio.connect() as con:
                doc = studio._get(con, pid)
                if operation == "transcribe":
                    doc.update(transcript=result, status="legendas")
                else:
                    doc.update(render=result, status="pronto")
                doc.update(error=None)
                studio._save(con, doc)
                studio.audit(con, operation+"_finished", pid)
            studio.export_brief(doc)
        except Exception as error:
            with studio.connect() as con:
                doc = studio._get(con, pid)
                doc.update(status="erro", error=str(error))
                studio._save(con, doc)
                studio.audit(con, operation+"_failed", pid, str(error))

    async def daily_loop():
        while True:
            if datetime.now(ZONE).hour >= 6:
                try:
                    await asyncio.to_thread(studio.generate)
                    app.state.schedule_error = None
                except Exception as error:
                    app.state.schedule_error = str(error)
            await asyncio.sleep(30)

    @asynccontextmanager
    async def lifespan(app):
        # One local server worker only. Interrupted tasks stay explicit and retryable.
        with studio.connect() as con:
            for row in con.execute("SELECT doc FROM productions").fetchall():
                doc = json.loads(row[0])
                if doc["status"] == "processando":
                    doc.update(status="erro", error="Processamento interrompido; repita a operação.")
                    studio._save(con, doc)
        task = asyncio.create_task(daily_loop()) if schedule else None
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        pool.shutdown(wait=True)

    app = FastAPI(title="Fazendeiro Studio", lifespan=lifespan)
    app.state.studio = studio
    app.state.schedule_error = None
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and origin != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site" or request.headers.get("x-local-action") != "1":
                return JSONResponse({"detail": "Ação local inválida"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/")
    def index():
        return FileResponse(PACKAGE/"static"/"index.html")

    app.mount("/static", StaticFiles(directory=PACKAGE/"static"), name="static")

    @app.get("/api/status")
    def status():
        with studio.connect() as con:
            credits = [dict(r) for r in con.execute("SELECT * FROM credits WHERE day=? ORDER BY created", (today(),))]
            campaign = json.loads(con.execute("SELECT value FROM settings WHERE key='campaign'").fetchone()[0])
        return {"date": today(), "credits_limit": 45, "credits_committed": sum(r["amount"] for r in credits if r["state"] != "refunded"),
                "credits": credits, "campaign": campaign, "schedule_enabled": schedule,
                "schedule_error": app.state.schedule_error, "flow_connected": False, "auto_publish": False,
                "character": json.loads((PACKAGE/"character.json").read_text())}

    @app.get("/api/productions")
    def productions():
        return studio.list()

    @app.post("/api/daily")
    def generate_daily():
        return studio.generate()

    @app.post("/api/productions/{pid}/credits")
    def reserve(pid: str, item: Reservation):
        return studio.reserve(pid, str(item.attempt), item.confirmed_cost, item.model, item.duration, item.resolution, item.generations)

    @app.post("/api/credits/{attempt}/{state}")
    def reconcile(attempt: str, state: Literal["charged", "uncertain", "refunded"]):
        with studio.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM credits WHERE attempt=?", (attempt,)).fetchone()
            if not row:
                raise ValueError("Tentativa não encontrada")
            if row["state"] == "refunded" and state != "refunded":
                raise ValueError("Reembolso encerrado; registre outra tentativa antes de gerar")
            con.execute("UPDATE credits SET state=? WHERE attempt=?", (state, attempt))
            studio.audit(con, "credit_"+state, row["production"], attempt)
        return {"state": state}

    @app.post("/api/productions/{pid}/upload/{kind}")
    def upload(pid: str, kind: Literal["source", "music", "sfx"], file: UploadFile = File(...), rights: str = Form(...), license: str = Form("")):
        if len(rights.strip()) < 10 or len(rights) > 2000:
            raise ValueError("Informe a origem e sua autorização para usar o arquivo")
        if kind != "source" and len(license.strip()) < 5:
            raise ValueError("Registre a licença e as condições de uso; não basta o áudio ser gratuito")
        suffix = Path(file.filename or "").suffix.lower()
        allowed = {".mp4", ".mov", ".webm"} if kind == "source" else {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
        if suffix not in allowed:
            raise ValueError("Formato de arquivo não suportado")
        doc = studio.get(pid)
        folder = studio.folder(doc)
        target = folder/(uuid.uuid4().hex + suffix)
        try:
            with target.open("xb") as out:
                size = 0
                while chunk := file.file.read(1024*1024):
                    size += len(chunk)
                    if size > 200*1024*1024:
                        raise ValueError("Limite de 200 MB por arquivo")
                    out.write(chunk)
            info = validate_source(target) if kind == "source" else probe(target)
            if kind != "source" and not any(s["codec_type"] == "audio" for s in info["streams"]):
                raise ValueError("Arquivo sem áudio")
            with studio.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                doc = studio._get(con, pid)
                studio.editable(doc)
                studio.invalidate(doc)
                doc[kind] = {"file": target.name, "sha256": fingerprint(target), "rights": rights.strip(), "license": license.strip(), "at": now()}
                if kind == "source":
                    doc.update(transcript=None, status="importado")
                else:
                    doc.update(status="legendas" if doc["transcript"] else "importado" if doc["source"] else "roteiro")
                studio._save(con, doc)
                studio.audit(con, "upload_"+kind, pid, json.dumps(doc[kind]))
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        studio.export_brief(doc)
        return doc

    @app.delete("/api/productions/{pid}/audio/{kind}")
    def remove_audio(pid: str, kind: Literal["music", "sfx"]):
        with studio.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            doc = studio._get(con, pid)
            studio.editable(doc)
            studio.invalidate(doc)
            doc[kind] = None
            doc["status"] = "legendas" if doc["transcript"] else "importado" if doc["source"] else "roteiro"
            studio._save(con, doc)
            studio.audit(con, "remove_"+kind, pid)
        return doc

    @app.post("/api/productions/{pid}/process/{operation}")
    def process(pid: str, operation: Literal["transcribe", "render"]):
        with studio.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            doc = studio._get(con, pid)
            studio.editable(doc)
            if not doc["source"]:
                raise ValueError("Importe primeiro o clipe do Flow")
            if operation == "render" and (not doc["transcript"] or not doc["transcript"].get("reviewed")):
                raise ValueError("Transcreva e revise as legendas antes de renderizar")
            studio.invalidate(doc)
            doc.update(status="processando", error=None)
            studio._save(con, doc)
            studio.audit(con, operation+"_queued", pid)
        pool.submit(work, pid, operation)
        return {"status": "processando"}

    @app.put("/api/productions/{pid}/transcript")
    def edit_transcript(pid: str, item: Transcript):
        segments = validate_segments(item.segments)
        with studio.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            doc = studio._get(con, pid)
            studio.editable(doc)
            if not doc["source"]:
                raise ValueError("Importe primeiro o clipe")
            studio.invalidate(doc)
            doc.update(transcript={"segments": segments, "reviewed": True, "model": (doc["transcript"] or {}).get("model", "manual"), "at": now()}, status="legendas")
            studio._save(con, doc)
            studio.audit(con, "review_transcript", pid)
        return doc

    @app.post("/api/productions/{pid}/approve")
    def approve(pid: str, item: Approval):
        return studio.approve(pid, item.model_dump())

    @app.post("/api/productions/{pid}/publication")
    def published(pid: str, item: Publication):
        return studio.published(pid, item.url)

    @app.get("/api/productions/{pid}/files/{name}")
    def download(pid: str, name: Literal["final.mp4", "captions.srt", "flow-prompt.txt", "description.txt", "brief.json"]):
        doc = studio.get(pid)
        if name == "final.mp4" and not doc["render"]:
            raise ValueError("Renderização indisponível ou desatualizada")
        path = studio.folder(doc)/name
        if not path.is_file():
            raise HTTPException(404, "Arquivo ainda não disponível")
        return FileResponse(path, media_type="video/mp4" if name == "final.mp4" else None,
                            filename=name, content_disposition_type="inline" if name == "final.mp4" else "attachment")

    @app.post("/api/productions/{pid}/metrics")
    def metrics(pid: str, item: Metric):
        if studio.get(pid)["status"] != "publicado":
            raise ValueError("Registre a publicação antes das métricas")
        if item.measured_at.tzinfo is None:
            raise ValueError("Data da medição precisa incluir fuso horário")
        return studio.add_metrics(pid, item.model_dump(mode="json"))

    @app.post("/api/metrics/import")
    def import_csv(file: UploadFile = File(...)):
        raw = file.file.read(1024*1024+1)
        if len(raw) > 1024*1024:
            raise ValueError("CSV maior que 1 MB")
        try:
            parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            validated = []
            for row in parsed:
                pid = row.pop("production_id")
                metric = Metric.model_validate(row)
                if metric.measured_at.tzinfo is None or studio.get(pid)["status"] != "publicado":
                    raise ValueError("Produção não publicada ou data sem fuso")
                validated.append((pid, metric.model_dump(mode="json")))
            if not validated:
                raise ValueError("CSV vazio")
        except (UnicodeError, KeyError, ValueError) as exc:
            raise ValueError("CSV inválido; use o modelo documentado. " + str(exc)) from exc
        with studio.connect() as con:
            for pid, item in validated:
                measured = datetime.fromisoformat(item["measured_at"]).astimezone(ZONE).isoformat()
                con.execute("INSERT INTO metrics VALUES(?,?,?) ON CONFLICT(production,measured_at) DO UPDATE SET doc=excluded.doc", (pid, measured, json.dumps(item)))
                studio.audit(con, "import_metrics", pid, measured)
        return {"imported": len(validated)}

    @app.get("/api/feedback")
    def feedback():
        return studio.feedback()

    @app.put("/api/followers")
    def followers(item: Followers):
        with studio.connect() as con:
            cfg = json.loads(con.execute("SELECT value FROM settings WHERE key='campaign'").fetchone()[0])
            cfg.update(current_followers=item.current_followers)
            con.execute("UPDATE settings SET value=? WHERE key='campaign'", (json.dumps(cfg),))
            studio.audit(con, "followers_snapshot", "account", json.dumps(item.model_dump()))
        return cfg

    return app


app = create_app(schedule=os.getenv("FARM_SCHEDULE", "1") == "1")
