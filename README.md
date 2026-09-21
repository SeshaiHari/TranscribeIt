# TranscribeIt

Free, offline video/audio transcription using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Works on Windows and macOS. No ffmpeg install or API key needed.

## Setup (Python 3.9+)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Desktop app

```bash
python app.py
```

Pick a file, choose a model, click **Transcribe**, then **Save…** to export as txt, srt or vtt.

## Command line

```bash
python transcribe.py videos/my-video/video.mp4                # -> videos/my-video/video.txt
python transcribe.py video.mp4 --format srt                   # subtitles
python transcribe.py video.mp4 --model tiny --language en     # faster, English only
```

Models: `tiny`, `base`, `small` (default), `medium`, `large-v3` — bigger is more accurate but slower. Models download once on first use.
