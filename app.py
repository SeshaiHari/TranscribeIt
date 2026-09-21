#!/usr/bin/env python3
"""Simple desktop app: pick a video/audio file, transcribe it locally, save the result."""
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import psutil

from transcribe_core import DEVICE_LABELS, FORMATS, MODELS, format_segments, transcribe

LANGUAGES = {
    "Auto-detect": None, "English": "en", "Hindi": "hi", "Telugu": "te", "Tamil": "ta",
    "Spanish": "es", "French": "fr", "German": "de", "Portuguese": "pt", "Japanese": "ja",
}
MODEL_HINTS = "tiny/base: fast, rough  ·  small: balanced  ·  medium/large-v3: most accurate, slow"
PAD = 20
PROGRESS_COLOR = "#10b981"  # emerald green
STAT_COLOR = "#6366f1"  # indigo

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TranscribeIt")
        self.geometry("780x640")
        self.minsize(640, 520)

        self.events = queue.Queue()
        self.segments = []
        self.busy = False
        self.device = "CPU"

        self.path_var = ctk.StringVar()
        self.model_var = ctk.StringVar(value="small")
        self.lang_var = ctk.StringVar(value="Auto-detect")
        self.format_var = ctk.StringVar(value="txt")
        self.status_var = ctk.StringVar(value="Choose a video or audio file to begin.")

        self._build()
        psutil.cpu_percent()  # prime: the first call always reports 0
        self.after(100, self._poll)
        self.after(500, self._update_stats)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        # File
        file_row = ctk.CTkFrame(self, fg_color="transparent")
        file_row.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))
        file_row.columnconfigure(0, weight=1)
        ctk.CTkEntry(file_row, textvariable=self.path_var, height=36,
                     placeholder_text="Select a video or audio file…").grid(
            row=0, column=0, sticky="ew")
        self.browse_btn = ctk.CTkButton(file_row, text="Browse", width=96, height=36,
                                        fg_color="transparent", border_width=1,
                                        text_color=("gray10", "gray90"),
                                        command=self._browse)
        self.browse_btn.grid(row=0, column=1, padx=(10, 0))

        # Options
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))
        for col, (label, var, values) in enumerate([
            ("Model", self.model_var, MODELS),
            ("Language", self.lang_var, list(LANGUAGES)),
            ("Export format", self.format_var, FORMATS),
        ]):
            ctk.CTkLabel(opts, text=label, anchor="w", text_color="gray").grid(
                row=0, column=col, sticky="w", padx=(0, PAD))
            ctk.CTkOptionMenu(opts, variable=var, values=values, width=150).grid(
                row=1, column=col, sticky="w", padx=(0, PAD), pady=(2, 0))
        ctk.CTkLabel(self, text=MODEL_HINTS, anchor="w", text_color="gray",
                     font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, sticky="w", padx=PAD, pady=(8, 0))

        # Actions + status
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=PAD, pady=(PAD, 0))
        actions.columnconfigure(2, weight=1)
        self.go_btn = ctk.CTkButton(actions, text="Transcribe", width=120, height=38,
                                    command=self._start)
        self.go_btn.grid(row=0, column=0)
        self.save_btn = ctk.CTkButton(actions, text="Save", width=96, height=38,
                                      fg_color="transparent", border_width=1,
                                      text_color=("gray10", "gray90"),
                                      state="disabled", command=self._save)
        self.save_btn.grid(row=0, column=1, padx=10)
        ctk.CTkLabel(actions, textvariable=self.status_var, anchor="e",
                     text_color="gray").grid(row=0, column=2, sticky="ew", padx=(PAD, 0))

        # Progress + transcript
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=4, column=0, sticky="nsew", padx=PAD, pady=PAD)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        self.progress = ctk.CTkProgressBar(body, height=10, progress_color=PROGRESS_COLOR,
                                           fg_color=("gray85", "gray25"))
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.text = ctk.CTkTextbox(body, wrap="word", state="disabled",
                                   font=ctk.CTkFont(size=14), border_width=1, corner_radius=8)
        self.text.grid(row=1, column=0, sticky="nsew")

        # System stats
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=5, column=0, sticky="ew", padx=PAD, pady=(0, PAD))
        stats.columnconfigure((1, 3), weight=1)
        self.cpu_label, self.cpu_bar = self._stat_bar(stats, 0, "CPU 0%")
        self.ram_label, self.ram_bar = self._stat_bar(stats, 2, "RAM 0%")

    @staticmethod
    def _stat_bar(parent, col, text):
        label = ctk.CTkLabel(parent, text=text, width=130, anchor="w", text_color="gray",
                             font=ctk.CTkFont(size=12))
        label.grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else PAD, 6))
        bar = ctk.CTkProgressBar(parent, height=6, progress_color=STAT_COLOR,
                                 fg_color=("gray85", "gray25"))
        bar.set(0)
        bar.grid(row=0, column=col + 1, sticky="ew")
        return label, bar

    def _update_stats(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        self.cpu_label.configure(text=f"CPU {cpu:.0f}%")
        self.cpu_bar.set(cpu / 100)
        self.ram_label.configure(
            text=f"RAM {mem.used / 2**30:.1f} / {mem.total / 2**30:.0f} GB")
        self.ram_bar.set(mem.percent / 100)
        self.after(1000, self._update_stats)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select a video or audio file",
            filetypes=[("Media files", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.m4a *.wav *.flac"),
                       ("All files", "*.*")])
        if path:
            self.path_var.set(path)
            self.status_var.set("Ready.")

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.go_btn.configure(state=state)
        self.browse_btn.configure(state=state)

    def _set_progress(self, fraction):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(fraction)

    def _start(self):
        path = Path(self.path_var.get().strip())
        if not path.is_file():
            messagebox.showerror("File not found", "Please choose an existing video or audio file.")
            return
        self.segments = []
        self._clear_text()
        self.save_btn.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.status_var.set("Loading model (first run downloads it)…")
        self._set_busy(True)

        args = (path, self.model_var.get(), LANGUAGES[self.lang_var.get()])
        threading.Thread(target=self._work, args=args, daemon=True).start()

    def _work(self, path, model, language):
        # Runs in a background thread; talks to the UI only through the queue.
        try:
            segments = transcribe(
                path, model, language,
                on_info=lambda info: self.events.put(("info", info)),
                on_segment=lambda item, total: self.events.put(("segment", item, total)),
                on_device=lambda name: self.events.put(("device", name)))
            self.events.put(("done", segments))
        except Exception as e:  # noqa: BLE001 - surface any failure in the UI
            self.events.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _handle(self, event):
        kind = event[0]
        if kind == "device":
            # Sent at the start of every attempt; a GPU failure restarts the run on the CPU.
            self.device = DEVICE_LABELS[event[1]]
            self._clear_text()
            self._set_progress(0)
            self.progress.configure(mode="indeterminate")
            self.progress.start()
            self.status_var.set(f"Loading model on {self.device} (first run downloads it)…")
        elif kind == "info":
            info = event[1]
            self._set_progress(0)
            self.status_var.set(f"Transcribing · {self.device} · {info.language} · "
                                f"{info.duration / 60:.1f} min")
        elif kind == "segment":
            _, item, total = event
            self._append(item["text"] + "\n")
            if total:
                self.progress.set(min(1, item["end"] / total))
        elif kind == "done":
            self.segments = event[1]
            self._set_progress(1)
            if self.segments:
                self.status_var.set(f"Done · {len(self.segments)} segments")
                self.save_btn.configure(state="normal")
            else:
                self.status_var.set("Done, but no speech was detected.")
            self._set_busy(False)
        elif kind == "error":
            self._set_progress(0)
            self.status_var.set("Failed.")
            self._set_busy(False)
            messagebox.showerror("Transcription failed", event[1])

    def _clear_text(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _append(self, s):
        self.text.configure(state="normal")
        self.text.insert("end", s)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _save(self):
        fmt = self.format_var.get()
        src = Path(self.path_var.get())
        out = filedialog.asksaveasfilename(
            title="Save transcript", defaultextension=f".{fmt}",
            initialdir=str(src.parent), initialfile=f"{src.stem}.{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}")])
        if out:
            Path(out).write_text(format_segments(self.segments, fmt), encoding="utf-8")
            self.status_var.set(f"Saved · {Path(out).name}")


if __name__ == "__main__":
    App().mainloop()
