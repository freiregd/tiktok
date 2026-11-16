from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PACKAGE = Path(__file__).parent
ZONE = ZoneInfo("America/Fortaleza")
MODEL = "Omni Flash 1.1"
RETIREMENT = date(2026, 12, 5)
DAILY_LIMIT = 45
UNIT_COST = 15


def today():
    return datetime.now(ZONE).date().isoformat()


def now():
    return datetime.now(ZONE).isoformat()


def fingerprint(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Studio:
    def __init__(self, root=None):
        self.root = Path(root or os.getenv("FARM_DATA", "data")).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "studio.sqlite3"
        with self.connect() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS productions (
                id TEXT PRIMARY KEY, day TEXT NOT NULL, slot INTEGER NOT NULL,
                doc TEXT NOT NULL, UNIQUE(day, slot));
            CREATE TABLE IF NOT EXISTS credits (
                attempt TEXT PRIMARY KEY, production TEXT NOT NULL,
                day TEXT NOT NULL, amount INTEGER NOT NULL,
                state TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS metrics (
                production TEXT NOT NULL, measured_at TEXT NOT NULL,
                doc TEXT NOT NULL, PRIMARY KEY(production, measured_at));
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY, at TEXT, action TEXT, production TEXT, details TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            con.execute("INSERT OR IGNORE INTO settings VALUES('campaign',?)", (json.dumps({"start": today(), "days": 7, "baseline_followers": 250, "current_followers": 250, "historical_views": 2000, "target_followers": 10000, "target_views": 100000, "count_historical_views": False}),))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def audit(self, con, action, pid, details=""):
        con.execute("INSERT INTO audit(at,action,production,details) VALUES(?,?,?,?)",
                    (now(), action, pid, details))

    def _get(self, con, pid):
        row = con.execute("SELECT doc FROM productions WHERE id=?", (pid,)).fetchone()
        if not row:
            raise ValueError("Produção não encontrada")
        return json.loads(row[0])

    def _save(self, con, doc):
        con.execute("UPDATE productions SET doc=? WHERE id=?", (json.dumps(doc, ensure_ascii=False), doc["id"]))

    def get(self, pid):
        with self.connect() as con:
            return self._get(con, pid)

    def list(self):
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute("SELECT doc FROM productions ORDER BY day DESC,slot")]

    def folder(self, doc):
        path = self.root / "productions" / doc["day"] / doc["id"]
        path.mkdir(parents=True, exist_ok=True)
        return path

    def feedback(self):
        """Compare latest snapshots; never add cumulative snapshots together."""
        rows = []
        with self.connect() as con:
            for p in con.execute("SELECT id,doc FROM productions"):
                m = con.execute("SELECT doc FROM metrics WHERE production=? ORDER BY measured_at DESC LIMIT 1", (p[0],)).fetchone()
                if m:
                    doc, metric = json.loads(p[1]), json.loads(m[0])
                    rows.append({"id": p[0], "title": doc["title"], "theme": doc["theme"], **metric})
        groups = {}
        for row in rows:
            if row["views"] < 300:
                continue
            g = groups.setdefault(row["theme"], {"views": 0, "followers": 0, "shares": 0, "n": 0})
            for k in ("views", "followers", "shares"):
                g[k] += row[k]
            g["n"] += 1
        ranking = [{"theme": t, **g, "followers_per_1000": round(1000*g["followers"]/g["views"], 2),
                    "shares_per_1000": round(1000*g["shares"]/g["views"], 2)} for t, g in groups.items()]
        ranking.sort(key=lambda g: (g["followers_per_1000"], g["shares_per_1000"]), reverse=True)
        return {"videos": rows, "ranking": ranking,
                "note": "Sinal exploratório; mínimo operacional de 300 views, sem significância estatística. Compare também idade dos posts e retenção."}

    def generate(self, day=None):
        day = day or today()
        date.fromisoformat(day)
        ranking = self.feedback()["ranking"]
        seeds = json.loads((PACKAGE / "ideas.json").read_text())
        character = json.loads((PACKAGE / "character.json").read_text())
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = [json.loads(r[0]) for r in con.execute("SELECT doc FROM productions WHERE day=? ORDER BY slot", (day,))]
            if existing:
                return existing
            used = {json.loads(r[0])["idea_id"] for r in con.execute("SELECT doc FROM productions")}
            available = [s for s in seeds if s["id"] not in used]
            if len(available) < 3:
                raise ValueError("Banco inicial de 21 roteiros esgotado. Acrescente ideias originais em ideas.json; não repetiremos vídeos automaticamente.")
            if ranking:
                preferred = ranking[0]["theme"]
                available.sort(key=lambda s: s["theme"] != preferred)
            chosen = []
            for seed in available:
                # Reserve one exploratory slot and avoid three copies of a theme.
                if sum(s["theme"] == seed["theme"] for s in chosen) < 2:
                    chosen.append(seed)
                if len(chosen) == 3:
                    break
            if len(chosen) < 3:
                chosen.extend(s for s in available if s not in chosen)
                chosen = chosen[:3]
            result = []
            for slot, seed in enumerate(chosen, 1):
                pid = uuid.uuid4().hex
                prompt = (
                    "Generate exactly ONE 10-second vertical 9:16 video, 720p, natural selfie-style realism. "
                    "Use the attached owner-provided reference image or saved Flow Character for the SAME fictional AI farmer. "
                    + character["visual"] + " " + character["setting"] + " " + character["voice"]
                    + " Action: " + seed["action"]
                    + " Timing: 0-2s start speaking immediately with eye contact; 2-8s deliver the scene; 8-10s finish naturally. "
                    + "Say EXACTLY in Brazilian Portuguese, without reading stage directions: «" + seed["line"] + "». "
                    "Keep stable identity, natural lip sync and hands, no extra people, no text overlays or invented logos. "
                    "No background music; only original voice and subtle farm ambience. Do not imitate a real person's voice. "
                    "Leave safe room for subtitles. Preserve required platform provenance/watermarks. "
                    "This is fictional AI entertainment, not a real farmer recording a personal invitation."
                )
                doc = {"id": pid, "day": day, "slot": slot, "idea_id": seed["id"],
                       "title": seed["title"], "theme": seed["theme"], "script": seed["line"],
                       "prompt": prompt, "description": seed["caption"] + " Personagem fictício e vídeo gerados por IA.",
                       "hashtags": ["#FazendeiroVirtual", "#VidaNaRoca", "#ProsaBoa", "#GeradoPorIA"],
                       "status": "roteiro", "character_version": character["version"], "character": character,
                       "flow": {"model": MODEL, "duration": 10, "resolution": "720p", "estimated_credits": UNIT_COST},
                       "source": None, "music": None, "sfx": None, "transcript": None,
                       "render": None, "approval": None, "publication": None, "error": None,
                       "created_at": now(), "revision": 0}
                con.execute("INSERT INTO productions VALUES(?,?,?,?)", (pid, day, slot, json.dumps(doc, ensure_ascii=False)))
                self.audit(con, "create_script", pid, seed["id"])
                result.append(doc)
        for doc in result:
            self.export_brief(doc)
        return result

    def export_brief(self, doc):
        f = self.folder(doc)
        (f / "brief.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
        (f / "flow-prompt.txt").write_text(doc["prompt"])
        (f / "description.txt").write_text(doc["description"] + "\n" + " ".join(doc["hashtags"]))

    def reserve(self, pid, attempt, confirmed_cost, model, duration, resolution, generations):
        if today() >= RETIREMENT.isoformat():
            raise ValueError("Modelo aposentado segundo a documentação consultada; reavalie custos antes de continuar.")
        if (confirmed_cost, model, duration, resolution, generations) != (15, MODEL, 10, "720p", 1):
            raise ValueError("Configuração divergente: exige Omni Flash 1.1, 10s, 720p, 1 geração, 15 créditos confirmados na tela.")
        uuid.UUID(attempt)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._get(con, pid)
            existing = con.execute("SELECT * FROM credits WHERE attempt=?", (attempt,)).fetchone()
            if existing:
                if existing["production"] != pid:
                    raise ValueError("Tentativa pertence a outra produção")
                return dict(existing)
            spent = con.execute("SELECT COALESCE(SUM(amount),0) FROM credits WHERE day=? AND state!='refunded'", (today(),)).fetchone()[0]
            if spent + UNIT_COST > DAILY_LIMIT:
                raise ValueError("Limite diário de 45 créditos atingido; tentativas incertas também contam.")
            con.execute("INSERT INTO credits VALUES(?,?,?,?,?,?)", (attempt, pid, today(), UNIT_COST, "reserved", now()))
            self.audit(con, "reserve_credits", pid, attempt)
        return {"attempt": attempt, "amount": UNIT_COST, "state": "reserved"}

    def credit_state(self, attempt, state):
        if state not in {"charged", "uncertain", "refunded"}:
            raise ValueError("Estado inválido")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM credits WHERE attempt=?", (attempt,)).fetchone()
            if not row:
                raise ValueError("Tentativa inexistente")
            con.execute("UPDATE credits SET state=? WHERE attempt=?", (state, attempt))
            self.audit(con, "credits_" + state, row["production"], attempt)

    def budget(self):
        with self.connect() as con:
            entries = [dict(r) for r in con.execute("SELECT * FROM credits WHERE day=? ORDER BY created", (today(),))]
        used = sum(r["amount"] for r in entries if r["state"] != "refunded")
        return {"day": today(), "limit": DAILY_LIMIT, "used_or_reserved": used,
                "remaining": DAILY_LIMIT-used, "entries": entries,
                "note": "Livro local manual; não consulta nem limita gastos feitos fora deste sistema no Flow."}

    def update(self, pid, action, fn):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            doc = self._get(con, pid)
            fn(doc)
            self._save(con, doc)
            self.audit(con, action, pid)
        self.export_brief(doc)
        return doc

    def editable(self, doc):
        if doc["status"] in {"processando", "publicado"}:
            raise ValueError("Produção em processamento ou já publicada; crie outra versão.")

    def invalidate(self, doc):
        doc.update(approval=None, render=None, revision=doc["revision"]+1, error=None)

    def approve(self, pid, checks):
        if not all(checks.get(k) is True for k in ("identity", "voice", "subtitles", "rights", "ai_label", "watched")):
            raise ValueError("Confirme todas as verificações após assistir ao vídeo final.")
        def change(doc):
            if doc["status"] != "pronto" or not doc["render"]:
                raise ValueError("É necessário renderizar antes de aprovar")
            path = self.folder(doc) / "final.mp4"
            digest = fingerprint(path)
            if digest != doc["render"]["sha256"]:
                raise ValueError("Arquivo alterado; renderize novamente")
            doc.update(status="aprovado", approval={"at": now(), "checks": checks, "sha256": digest})
        return self.update(pid, "approve", change)

    def published(self, pid, url):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.tiktok.com", "tiktok.com", "vm.tiktok.com", "vt.tiktok.com"} or not parsed.path.strip("/"):
            raise ValueError("Informe o link HTTPS do vídeo publicado no TikTok")
        def change(doc):
            if doc["status"] != "aprovado" or not doc["approval"]:
                raise ValueError("Aprovação obrigatória antes de registrar publicação")
            if fingerprint(self.folder(doc)/"final.mp4") != doc["approval"]["sha256"]:
                raise ValueError("Arquivo mudou depois da aprovação")
            doc.update(status="publicado", publication={"url": url, "recorded_at": now()})
        return self.update(pid, "record_manual_publication", change)

    def add_metrics(self, pid, metric):
        if self.get(pid)["status"] != "publicado":
            raise ValueError("Registre a publicação antes das métricas")
        stamp = datetime.fromisoformat(metric["measured_at"])
        if stamp.tzinfo is None:
            raise ValueError("Data das métricas exige fuso horário")
        metric["measured_at"] = stamp.astimezone(ZONE).isoformat()
        with self.connect() as con:
            con.execute("INSERT INTO metrics VALUES(?,?,?) ON CONFLICT(production,measured_at) DO UPDATE SET doc=excluded.doc",
                        (pid, metric["measured_at"], json.dumps(metric)))
            self.audit(con, "metrics_snapshot", pid, metric["measured_at"])
        return self.feedback()
