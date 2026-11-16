from __future__ import annotations

import json
import math
import os
import re
import subprocess
import uuid
from pathlib import Path

from .core import Studio, fingerprint, now


def run(args, cwd=None, timeout=300):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError("Falha no FFmpeg/ffprobe: " + result.stderr[-1800:])
    return result.stdout


def probe(path):
    info = json.loads(run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(Path(path).resolve())], timeout=30))
    duration = float(info.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0 or duration > 180:
        raise ValueError("Duração inválida ou maior que 180 segundos")
    return info


def validate_source(path):
    info = probe(path)
    streams = info["streams"]
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    if not video or not any(s["codec_type"] == "audio" for s in streams):
        raise ValueError("O clipe precisa conter vídeo e voz. Gere com áudio no Flow.")
    if video.get("width", 0) * video.get("height", 0) > 3840*2160:
        raise ValueError("Resolução acima de 4K não suportada")
    if not 9.5 <= float(info["format"]["duration"]) <= 10.5:
        raise ValueError("Este sprint exige clipes de 10s (tolerância de 0,5s). Não corte falas para caber.")
    return info


def validate_segments(segments, duration=10):
    if not segments:
        raise ValueError("Nenhuma fala encontrada. Confira o áudio; não usaremos legendas com tempos inventados.")
    previous = 0.0
    result = []
    for s in segments:
        try:
            start, end = float(s["start"]), float(s["end"])
            text = str(s["text"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Cada legenda exige start, end e text válidos") from exc
        if not all(math.isfinite(n) for n in (start, end)) or not 0 <= start < end <= duration+0.05 or start < previous-0.02:
            raise ValueError("Tempos das legendas inválidos, sobrepostos ou fora do vídeo")
        if not text or len(text) > 180:
            raise ValueError("Legenda vazia ou longa demais; divida em trechos menores")
        result.append({"start": round(start, 3), "end": round(min(end, duration), 3), "text": text})
        previous = end
    return result


def stamp(seconds, ass=False):
    units = round(seconds*(100 if ass else 1000))
    base = 100 if ass else 1000
    seconds, frac = divmod(units, base)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}.{frac:02d}" if ass else f"{hours:02d}:{minutes:02d}:{sec:02d},{frac:03d}"


def subtitle_files(folder, segments, width=1080, height=1920):
    srt = "\n\n".join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i, s in enumerate(segments, 1))
    (folder / "captions.srt").write_text(srt + "\n")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{int(height*.028)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,{int(width*.1)},{int(width*.18)},{int(height*.23)},1
Style: Label,DejaVu Sans,{int(height*.018)},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,3,1,0,8,20,20,{int(height*.12)},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 1,0:00:00.00,0:00:10.00,Label,,0,0,0,,PERSONAGEM E VÍDEO GERADOS POR IA
"""
    lines = []
    for s in segments:
        # Strip ASS control syntax from untrusted recognized/user text.
        text = re.sub(r"[{}\\\r\n]", " ", s["text"])
        lines.append(f"Dialogue: 0,{stamp(s['start'], True)},{stamp(s['end'], True)},Default,,0,0,0,,{text}")
    (folder/"captions.ass").write_text(header + "\n".join(lines)+"\n")


def transcribe(studio: Studio, doc, model="tiny"):
    os.environ.setdefault("HF_HOME", str(studio.root/"models"/"cache"))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from faster_whisper import WhisperModel
    folder = studio.folder(doc)
    src = folder/doc["source"]["file"]
    run(["ffmpeg", "-y", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(src), "-t", "10", "-vn", "-ac", "1", "-ar", "16000", str(folder/"voice.wav")])
    recognizer = WhisperModel(model, device="cpu", compute_type="int8", download_root=str(studio.root/"models"), cpu_threads=2)
    recognized, info = recognizer.transcribe(str(folder/"voice.wav"), language="pt", beam_size=5, word_timestamps=True, vad_filter=True)
    captions, pending = [], []
    for segment in recognized:
        for word in segment.words or []:
            text = word.word.strip()
            if not text or word.end <= word.start or word.start >= 10:
                continue
            pending.append({"text": text, "start": word.start, "end": min(word.end, 10)})
            if len(pending) >= 5 or len(" ".join(w["text"] for w in pending)) >= 32 or text.endswith((".", "?", "!")):
                captions.append({"start": pending[0]["start"], "end": pending[-1]["end"], "text": " ".join(w["text"] for w in pending)})
                pending = []
    if pending:
        captions.append({"start": pending[0]["start"], "end": pending[-1]["end"], "text": " ".join(w["text"] for w in pending)})
    captions = validate_segments(captions)
    (folder/"whisper.json").write_text(json.dumps({"model": model, "language": info.language, "segments": captions}, ensure_ascii=False, indent=2))
    return {"model": model, "segments": captions, "reviewed": False, "at": now()}


def render(studio: Studio, doc, width=1080, height=1920, zoom=True):
    folder = studio.folder(doc)
    validate_source(folder/doc["source"]["file"])
    if not doc["transcript"] or not doc["transcript"].get("reviewed"):
        raise ValueError("Revise as legendas sincronizadas antes de renderizar")
    segments = validate_segments(doc["transcript"]["segments"])
    subtitle_files(folder, segments, width, height)
    args = ["ffmpeg", "-y", "-v", "error", "-threads", "2", "-filter_complex_threads", "1", "-protocol_whitelist", "file,pipe", "-i", doc["source"]["file"]]
    extra = []
    for kind in ("music", "sfx"):
        asset = doc.get(kind)
        if asset:
            if not asset.get("rights") or not asset.get("license"):
                raise ValueError("Áudio sem registro de licença")
            if fingerprint(folder/asset["file"]) != asset["sha256"]:
                raise ValueError("Áudio mudou após o registro de licença")
            if kind == "music":
                args += ["-stream_loop", "-1"]
            args += ["-protocol_whitelist", "file,pipe", "-i", asset["file"]]
            extra.append(kind)
    inset_w, inset_h = int(width*.94)//2*2, int(height*.94)//2*2
    video = f"[0:v]scale={inset_w}:{inset_h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=1,trim=duration=10,setpts=PTS-STARTPTS"
    if zoom:
        # Zoom only into padding: the entire source and provenance remain visible.
        video += f",zoompan=z='1+0.02*on/300':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=30"
    video += ",subtitles=captions.ass[v]"
    filters = [video, "[0:a]aresample=48000,apad,atrim=duration=10,asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11[voice]"]
    labels = ["[voice]"]
    for index, kind in enumerate(extra, 1):
        label = f"a{index}"
        volume = "0.09" if kind == "music" else "0.14"
        delay = ",adelay=2000|2000" if kind == "sfx" else ""
        filters.append(f"[{index}:a]aresample=48000,asetpts=PTS-STARTPTS,volume={volume}{delay},apad,atrim=duration=10[{label}]")
        labels.append(f"[{label}]")
    filters.append("".join(labels)+f"amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    temp = "render-" + uuid.uuid4().hex + ".mp4"
    args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-t", "10", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", temp]
    try:
        run(args, cwd=folder, timeout=300)
        info = probe(folder/temp)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        if (v["width"], v["height"]) != (width, height) or abs(float(info["format"]["duration"])-10) > .15:
            raise ValueError("Exportação fora da especificação")
        (folder/temp).replace(folder/"final.mp4")
    finally:
        (folder/temp).unlink(missing_ok=True)
    return {"at": now(), "sha256": fingerprint(folder/"final.mp4"), "width": width, "height": height,
            "duration": 10, "zoom": zoom, "ai_disclosure": True, "audio_assets": {k: doc[k] for k in extra}}
