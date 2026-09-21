"""Shared transcription logic used by the CLI (transcribe.py) and the desktop app (app.py).

Engines, tried in order until one works:
  mlx   Apple Silicon GPU via mlx-whisper (macOS arm64 only, optional dependency)
  cuda  NVIDIA GPU via faster-whisper (Windows/Linux with CUDA libraries)
  cpu   faster-whisper on all CPU cores (works everywhere)
"""
import os
import platform
import sys
from types import SimpleNamespace

import ctranslate2
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
FORMATS = ["txt", "srt", "vtt"]
DEVICE_LABELS = {"mlx": "Apple GPU", "cuda": "NVIDIA GPU", "cpu": "CPU"}

SAMPLE_RATE = 16_000
MLX_CHUNK_SECONDS = 300  # mlx-whisper has no streaming, so transcribe in chunks for progress


class AudioError(RuntimeError):
    """The input has no readable audio; retrying on another device won't help."""


def _timestamp(seconds: float, sep: str) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{sep}{ms:03}"


def format_segments(segments, fmt: str) -> str:
    if fmt == "txt":
        return "\n".join(s["text"] for s in segments) + "\n"
    sep = "," if fmt == "srt" else "."
    lines = ["WEBVTT", ""] if fmt == "vtt" else []
    for i, s in enumerate(segments, 1):
        if fmt == "srt":
            lines.append(str(i))
        lines.append(f"{_timestamp(s['start'], sep)} --> {_timestamp(s['end'], sep)}")
        lines.append(s["text"])
        lines.append("")
    return "\n".join(lines)


def _mlx_available():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _cuda_available():
    try:
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - build without CUDA support
        return False


def _devices():
    """Engines to try in order; the CPU is always the last resort."""
    if _mlx_available():
        return ["mlx", "cpu"]
    return (["cuda"] if _cuda_available() else []) + ["cpu"]


def _load_audio(path):
    try:
        return decode_audio(str(path), sampling_rate=SAMPLE_RATE)
    except (IndexError, ValueError) as e:
        raise AudioError(f"Could not read audio from {path} (no audio track?)") from e


def _run_mlx(path, model_name, language, on_info, on_segment):
    import mlx_whisper

    audio = _load_audio(path)
    duration = len(audio) / SAMPLE_RATE
    repo = f"mlx-community/whisper-{model_name}-mlx"
    chunk = MLX_CHUNK_SECONDS * SAMPLE_RATE
    segments = []
    for start in range(0, len(audio), chunk):
        result = mlx_whisper.transcribe(audio[start:start + chunk], path_or_hf_repo=repo,
                                        language=language, verbose=None)
        if start == 0:
            language = language or result["language"]  # keep later chunks on the same language
            if on_info:
                on_info(SimpleNamespace(language=language, language_probability=None,
                                        duration=duration))
        offset = start / SAMPLE_RATE
        for seg in result["segments"]:
            text = seg["text"].strip()
            if not text:
                continue
            item = {"start": offset + seg["start"], "end": offset + seg["end"], "text": text}
            segments.append(item)
            if on_segment:
                on_segment(item, duration)
    return segments


def _run_faster_whisper(path, model_name, language, device, on_info, on_segment):
    if device == "cuda":
        model = WhisperModel(model_name, device="cuda", compute_type="float16")
    else:
        model = WhisperModel(model_name, device="cpu", compute_type="int8",
                             cpu_threads=os.cpu_count() or 4)
    try:
        seg_iter, info = model.transcribe(str(path), language=language, vad_filter=True)
    except (IndexError, ValueError) as e:
        raise AudioError(f"Could not read audio from {path} (no audio track?)") from e
    if on_info:
        on_info(info)
    segments = []
    # transcribe() is lazy: missing GPU libraries only fail once segments are pulled.
    for seg in seg_iter:
        item = {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        segments.append(item)
        if on_segment:
            on_segment(item, info.duration)
    return segments


def transcribe(path, model_name="small", language=None, on_info=None, on_segment=None,
               on_device=None):
    """Return a list of {start, end, text} dicts.

    on_device(name) is called before each attempt with "mlx", "cuda" or "cpu"; if a GPU
    attempt fails, it is called again with the next engine and the run restarts.
    on_info(info) is called once the audio was opened (info.language, info.duration).
    on_segment(item, total_duration) is called for every segment as it is produced.
    """
    devices = _devices()
    for device in devices:
        if on_device:
            on_device(device)
        try:
            if device == "mlx":
                return _run_mlx(path, model_name, language, on_info, on_segment)
            return _run_faster_whisper(path, model_name, language, device, on_info, on_segment)
        except AudioError:
            raise
        except Exception:  # noqa: BLE001
            if device == devices[-1]:
                raise
            # GPU failed (missing libraries, out of memory, ...): fall back to the next engine.
