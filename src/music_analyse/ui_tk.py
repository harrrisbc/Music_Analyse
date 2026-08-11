"""Native tkinter control panel for Music Analyse (no web UI)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from music_analyse import config
from music_analyse.audio.source import list_input_devices
from music_analyse.engine import Engine
from music_analyse.banks import (
    BANK_PRESETS,
    BankParams,
    default_banks,
    hz_to_pos,
    pos_to_hz,
)
from music_analyse.output.addresses import BANK_IDS, FLOATS, TRIGGERS
from music_analyse.output.midi_out import list_midi_output_names
from music_analyse.tune import PRESETS, TuneParams, preset_normal

BG = "#0d0d0d"
FG = "#e8e8e8"
MUTED_FG = "#888888"
ACCENT = "#2ee6a6"
ERROR = "#ff6b6b"
BAR_BG = "#1a1a1a"

UI_POLL_MS = 50


class MusicAnalyseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Music Analyse")
        self.configure(bg=BG)
        self.minsize(520, 480)
        self.geometry("560x720")
        self.engine = Engine()
        self._file_path: str | None = None
        self._meter_fills: dict[str, tk.Frame] = {}
        self._meter_labels: dict[str, tk.Label] = {}
        self._trig_labels: dict[str, tk.Label] = {}
        self._tune_expanded = False
        self._tune_applying = False
        self._banks_expanded = False
        self._banks_applying = False

        self._build_style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(UI_POLL_MS, self._poll)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED_FG)
        style.configure("Header.TLabel", background=BG, foreground=FG, font=("Helvetica", 16, "bold"))
        style.configure("Section.TLabel", background=BG, foreground=ACCENT, font=("Helvetica", 11, "bold"))
        style.configure("TRadiobutton", background=BG, foreground=FG)
        style.map("TRadiobutton", background=[("active", BG)], foreground=[("active", FG), ("!disabled", FG)])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map(
            "TCheckbutton",
            background=[("active", BG), ("!disabled", BG)],
            foreground=[("active", FG), ("!disabled", FG)],
        )
        style.configure("TButton", background=BAR_BG, foreground=FG)
        style.map("TButton", background=[("active", "#222222")], foreground=[("active", FG), ("!disabled", FG)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#0d0d0d")
        style.map("Accent.TButton", background=[("active", "#5ef0c0")])
        style.configure("MuteOn.TButton", background=ACCENT, foreground="#0d0d0d")
        style.map("MuteOn.TButton", background=[("active", "#5ef0c0")])
        style.configure("MuteOff.TButton", background=BAR_BG, foreground=MUTED_FG)
        style.configure("TEntry", fieldbackground=BAR_BG, foreground=FG, insertcolor=FG)
        style.map(
            "TEntry",
            fieldbackground=[("!disabled", BAR_BG), ("readonly", BAR_BG)],
            foreground=[("!disabled", FG)],
        )
        style.configure("TCombobox", fieldbackground=BAR_BG, foreground=FG, background=BAR_BG)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", BAR_BG), ("!disabled", BAR_BG)],
            foreground=[("readonly", FG), ("!disabled", FG)],
            background=[("readonly", BAR_BG), ("!disabled", BAR_BG)],
        )
        style.configure("Horizontal.TScale", background=BG, troughcolor=BAR_BG, foreground=FG)
        style.map("Horizontal.TScale", background=[("active", BG)], foreground=[("active", FG)])

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(shell, bg=BG, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        root = ttk.Frame(self.canvas, style="TFrame")
        self._canvas_win = self.canvas.create_window((0, 0), window=root, anchor="nw")
        root.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel()

        inner_pad = ttk.Frame(root, style="TFrame")
        inner_pad.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        root = inner_pad

        ttk.Label(root, text="Music Analyse", style="Header.TLabel").pack(anchor="w", **pad)

        # --- 1. Source ---
        ttk.Label(root, text="1. Source", style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        src = ttk.Frame(root)
        src.pack(fill=tk.X, **pad)

        self.mode_var = tk.StringVar(value="File")
        mode_row = ttk.Frame(src)
        mode_row.pack(fill=tk.X)
        ttk.Radiobutton(
            mode_row, text="File", value="File", variable=self.mode_var, command=self._on_mode
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            mode_row, text="Live", value="Live", variable=self.mode_var, command=self._on_mode
        ).pack(side=tk.LEFT)

        self.file_frame = ttk.Frame(src)
        self.file_frame.pack(fill=tk.X, pady=(8, 0))
        self.file_var = tk.StringVar(value="(no file selected)")
        ttk.Label(self.file_frame, textvariable=self.file_var, style="Muted.TLabel").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(self.file_frame, text="Browse…", command=self._browse).pack(side=tk.RIGHT)

        self.live_frame = ttk.Frame(src)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(
            self.live_frame, textvariable=self.device_var, state="readonly"
        )
        self.device_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(self.live_frame, text="Refresh", command=self._refresh_ports).pack(
            side=tk.RIGHT, padx=(8, 0)
        )

        self.hint_var = tk.StringVar(value="Select a file to enable Start.")
        ttk.Label(root, textvariable=self.hint_var, style="Muted.TLabel").pack(anchor="w", padx=12)

        # --- 2. Transport ---
        ttk.Label(root, text="2. Transport", style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        tr = ttk.Frame(root)
        tr.pack(fill=tk.X, **pad)
        self.start_btn = ttk.Button(tr, text="Start", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn = ttk.Button(tr, text="Stop", command=self._stop)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.mute_btn = ttk.Button(tr, text="MUTED", style="MuteOn.TButton", command=self._toggle_mute)
        self.mute_btn.pack(side=tk.LEFT)
        self.mute_hint = ttk.Label(tr, text="", style="Muted.TLabel")
        self.mute_hint.pack(side=tk.LEFT, padx=(8, 0))

        # --- 3. Outputs ---
        ttk.Label(root, text="3. Outputs", style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        out = ttk.Frame(root)
        out.pack(fill=tk.X, **pad)

        osc_row = ttk.Frame(out)
        osc_row.pack(fill=tk.X, pady=2)
        self.osc_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(osc_row, text="OSC", variable=self.osc_enabled).pack(side=tk.LEFT)
        self.osc_host = tk.StringVar(value=config.OSC_HOST)
        self.osc_port = tk.StringVar(value=str(config.OSC_PORT))
        ttk.Entry(osc_row, textvariable=self.osc_host, width=14).pack(side=tk.LEFT, padx=6)
        ttk.Entry(osc_row, textvariable=self.osc_port, width=6).pack(side=tk.LEFT)

        midi_row = ttk.Frame(out)
        midi_row.pack(fill=tk.X, pady=2)
        self.midi_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(midi_row, text="MIDI", variable=self.midi_enabled).pack(side=tk.LEFT)
        self.midi_port = tk.StringVar(value=config.MIDI_PORT_NAME)
        self.midi_combo = ttk.Combobox(midi_row, textvariable=self.midi_port)
        self.midi_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        # --- 4. Monitor ---
        ttk.Label(root, text="4. Monitor", style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        mon = ttk.Frame(root)
        mon.pack(fill=tk.X, **pad)

        trig_row = ttk.Frame(mon)
        trig_row.pack(fill=tk.X, pady=(0, 8))
        for name in TRIGGERS:
            lbl = tk.Label(
                trig_row,
                text=name,
                width=8,
                bg=BAR_BG,
                fg=MUTED_FG,
                font=("Menlo", 11),
                padx=6,
                pady=6,
            )
            lbl.pack(side=tk.LEFT, padx=3)
            self._trig_labels[name] = lbl

        for name in FLOATS:
            row = ttk.Frame(mon)
            row.pack(fill=tk.X, pady=3)
            lab = tk.Label(
                row,
                text=f"{name}: 0.00",
                width=28,
                anchor="w",
                bg=BG,
                fg=FG,
                font=("Menlo", 11),
            )
            lab.pack(side=tk.LEFT)
            self._meter_labels[name] = lab
            track = tk.Frame(row, bg=BAR_BG, height=10)
            track.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
            track.pack_propagate(False)
            fill = tk.Frame(track, bg=ACCENT, width=1, height=10)
            fill.place(x=0, y=0, relheight=1.0, width=1)
            self._meter_fills[name] = fill
            fill._track = track  # type: ignore[attr-defined]

        # Heartbeat scope (~3s conditioned float)
        scope_bar = ttk.Frame(mon)
        scope_bar.pack(fill=tk.X, pady=(10, 2))
        ttk.Label(scope_bar, text="Scope", style="Muted.TLabel").pack(side=tk.LEFT)
        self.scope_channel = tk.StringVar(value=config.SCOPE_DEFAULT_CHANNEL)
        self.scope_combo = ttk.Combobox(
            scope_bar,
            textvariable=self.scope_channel,
            values=["vocal_presence", "rms", "onset_strength", "bass_energy", *BANK_IDS],
            state="readonly",
            width=18,
        )
        self.scope_combo.pack(side=tk.LEFT, padx=8)
        self.scope_combo.bind("<<ComboboxSelected>>", lambda _e: self._draw_scope())
        ttk.Label(scope_bar, text="3.0s", style="Muted.TLabel").pack(side=tk.LEFT)
        self.scope_canvas = tk.Canvas(
            mon, height=90, bg=BAR_BG, highlightthickness=0, bd=0
        )
        self.scope_canvas.pack(fill=tk.X, pady=(2, 0))
        self.scope_canvas.bind("<Configure>", lambda _e: self._draw_scope())

        # --- 5. Tune (collapsed) ---
        self.tune_header = ttk.Button(
            root, text="▸ 5. Tune", command=self._toggle_tune, style="TButton"
        )
        self.tune_header.pack(anchor="w", padx=12, pady=(10, 2))
        self.tune_body = ttk.Frame(root)

        preset_row = ttk.Frame(self.tune_body)
        preset_row.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(preset_row, text="Preset:", style="Muted.TLabel").pack(side=tk.LEFT)
        for name in ("Gentle", "Normal", "Tight", "Kick safe"):
            ttk.Button(
                preset_row, text=name, command=lambda n=name: self._apply_preset(n)
            ).pack(side=tk.LEFT, padx=3)

        ttk.Label(self.tune_body, text="Floats (dynamics)", style="Muted.TLabel").pack(
            anchor="w", padx=12, pady=(8, 2)
        )
        self._sliders: dict[str, tuple[tk.DoubleVar, ttk.Label]] = {}
        self._add_slider(
            self.tune_body, "threshold", "Threshold", 0.0, 0.1, 0.01,
            "Ignore levels below this",
        )
        self._add_slider(
            self.tune_body, "amount", "Amount", 0.0, 1.0, 0.05,
            "How hard levels are normalized",
        )
        self._add_slider(
            self.tune_body, "attack_s", "Attack", 0.005, 0.1, 0.001,
            "How fast levels rise",
        )
        self._add_slider(
            self.tune_body, "release_s", "Release", 0.05, 1.0, 0.01,
            "How fast levels fall",
        )
        self._add_slider(
            self.tune_body, "makeup", "Makeup", 0.5, 2.0, 0.05,
            "Boost after dynamics",
        )

        ttk.Label(self.tune_body, text="Triggers", style="Muted.TLabel").pack(
            anchor="w", padx=12, pady=(8, 2)
        )
        self._add_slider(
            self.tune_body, "sensitivity", "Sensitivity", 0.0, 1.0, 0.05,
            "More / fewer triggers",
        )
        self._add_slider(
            self.tune_body, "hold_ms", "Hold", 20.0, 300.0, 5.0,
            "Min time between bangs (ms)",
        )
        self._add_slider(
            self.tune_body, "kick_strictness", "Kick strictness", 0.0, 1.0, 0.05,
            "Reject pitched lows (piano)",
        )

        # --- 6. Banks (collapsed) ---
        self.banks_header = ttk.Button(
            root, text="▸ 6. Banks", command=self._toggle_banks, style="TButton"
        )
        self.banks_header.pack(anchor="w", padx=12, pady=(10, 2))
        self.banks_body = ttk.Frame(root)
        bank_preset_row = ttk.Frame(self.banks_body)
        bank_preset_row.pack(fill=tk.X, padx=12, pady=4)
        ttk.Label(bank_preset_row, text="Bank presets:", style="Muted.TLabel").pack(side=tk.LEFT)
        for name in ("Kick-ish", "Snare-ish", "Hat-ish", "Reset"):
            ttk.Button(
                bank_preset_row, text=name, command=lambda n=name: self._apply_bank_preset(n)
            ).pack(side=tk.LEFT, padx=3)

        self._bank_widgets: list[dict] = []
        for i in range(1, 5):
            self._bank_widgets.append(self._build_bank_block(self.banks_body, i))

        # --- 7. Status ---
        ttk.Label(root, text="7. Status", style="Section.TLabel").pack(anchor="w", padx=12, pady=(10, 2))
        self.status_var = tk.StringVar(value="idle")
        self.error_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(
            root, textvariable=self.status_var, bg=BG, fg=MUTED_FG, font=("Menlo", 12), anchor="w"
        )
        self.status_lbl.pack(fill=tk.X, padx=12)
        tk.Label(
            root, textvariable=self.error_var, bg=BG, fg=ERROR, font=("Menlo", 11), anchor="w"
        ).pack(fill=tk.X, padx=12, pady=(0, 8))

        self._load_tune_into_sliders(preset_normal())
        self.engine.apply_tune(preset_normal())
        self._load_banks_into_ui(default_banks())
        self.engine.apply_banks(default_banks())
        self.engine.set_mute(True)
        self._refresh_mute_ui()

        # Do not probe MIDI on launch — rtmidi/CoreMIDI can abort the process.
        self.midi_combo["values"] = [config.MIDI_PORT_NAME]
        self._refresh_audio_devices()
        self._on_mode()
        self._update_start_enabled()

    def _add_slider(
        self,
        parent: ttk.Frame,
        key: str,
        label: str,
        lo: float,
        hi: float,
        step: float,
        tip: str,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, padx=12, pady=2)
        tk.Label(row, text=label, width=14, bg=BG, fg=FG, anchor="w").pack(side=tk.LEFT)
        var = tk.DoubleVar(value=lo)
        val_lbl = tk.Label(row, text="0.00", width=7, bg=BG, fg=FG, anchor="e")
        val_lbl.pack(side=tk.RIGHT)
        scale = ttk.Scale(
            row,
            from_=lo,
            to=hi,
            variable=var,
            orient=tk.HORIZONTAL,
            command=lambda _v, k=key: self._on_tune_change(k),
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        # Tooltip via status-bar style: bind Enter
        scale.bind("<Enter>", lambda _e, t=tip: self.hint_var.set(t))
        scale.bind("<Leave>", lambda _e: self._restore_hint())
        self._sliders[key] = (var, val_lbl)

    def _restore_hint(self) -> None:
        if not self._source_ok():
            if self.mode_var.get() == "File":
                self.hint_var.set("Select a file to enable Start.")
            else:
                self.hint_var.set("Select an input device to enable Start.")
        else:
            self.hint_var.set("")

    def _on_inner_configure(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._canvas_win, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = int(event.delta)
        if delta == 0:
            return
        steps = int(-delta / 120) if abs(delta) >= 120 else int(-delta)
        if steps:
            self.canvas.yview_scroll(steps, "units")

    def _bind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))

    def _unbind_mousewheel(self, _event: tk.Event | None = None) -> None:
        self.unbind_all("<MouseWheel>")
        self.unbind_all("<Button-4>")
        self.unbind_all("<Button-5>")

    def _build_bank_block(self, parent: ttk.Frame, index: int) -> dict:
        box = ttk.Frame(parent)
        box.pack(fill=tk.X, padx=12, pady=6)

        top = ttk.Frame(box)
        top.pack(fill=tk.X)
        enabled = tk.BooleanVar(value=index != 4)
        tk.Checkbutton(
            top,
            text=f"Bank {index}",
            variable=enabled,
            command=self._on_banks_change,
            bg=BG,
            fg=FG,
            selectcolor=BAR_BG,
            activebackground=BG,
            activeforeground=FG,
            highlightthickness=0,
        ).pack(side=tk.LEFT)
        name_var = tk.StringVar(value=f"Bank {index}")
        tk.Entry(
            top,
            textvariable=name_var,
            width=14,
            bg=BAR_BG,
            fg=FG,
            insertbackground=FG,
            highlightthickness=1,
            highlightbackground="#333333",
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=6)
        name_var.trace_add("write", lambda *_: self._on_banks_change())
        flash = tk.Label(top, text="bang", width=6, bg=BAR_BG, fg=FG, font=("Menlo", 10), padx=4, pady=2)
        flash.pack(side=tk.RIGHT)
        err = tk.Label(top, text="", bg=BG, fg=ERROR)
        err.pack(side=tk.RIGHT, padx=6)

        lo_var = tk.DoubleVar(value=hz_to_pos(40.0))
        hi_var = tk.DoubleVar(value=hz_to_pos(120.0))
        thr_var = tk.DoubleVar(value=0.55)

        lo_val = self._bank_slider_row(box, "Low", lo_var, 0.0, 1.0)
        hi_val = self._bank_slider_row(box, "High", hi_var, 0.0, 1.0)
        thr_row = tk.Frame(box, bg=BG)
        thr_row.pack(fill=tk.X, pady=3)
        tk.Label(
            thr_row, text="Threshold", width=10, bg=BG, fg=FG, anchor="w", font=("Helvetica", 12)
        ).pack(side=tk.LEFT)
        ttk.Scale(
            thr_row,
            from_=0.05,
            to=0.95,
            variable=thr_var,
            orient=tk.HORIZONTAL,
            command=lambda _v: self._on_banks_change(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        thr_val = tk.Label(
            thr_row,
            text="0.55",
            width=10,
            bg=ACCENT,
            fg="#0d0d0d",
            font=("Menlo", 13, "bold"),
            padx=8,
            pady=3,
        )
        thr_val.pack(side=tk.RIGHT)
        track = tk.Frame(box, bg=BAR_BG, height=10)
        track.pack(fill=tk.X, pady=(2, 0))
        track.pack_propagate(False)
        fill = tk.Frame(track, bg=ACCENT, width=1, height=10)
        fill.place(x=0, y=0, relheight=1.0, width=1)
        fill._track = track  # type: ignore[attr-defined]

        return {
            "index": index,
            "enabled": enabled,
            "name": name_var,
            "lo": lo_var,
            "hi": hi_var,
            "thr": thr_var,
            "lo_lbl": lo_val,
            "hi_lbl": hi_val,
            "thr_lbl": thr_val,
            "err": err,
            "flash": flash,
            "fill": fill,
        }

    def _bank_slider_row(
        self,
        parent: tk.Widget,
        caption: str,
        var: tk.DoubleVar,
        lo: float,
        hi: float,
    ) -> tk.Label:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill=tk.X, pady=3)
        tk.Label(
            row, text=caption, width=10, bg=BG, fg=FG, anchor="w", font=("Helvetica", 12)
        ).pack(side=tk.LEFT)
        ttk.Scale(
            row,
            from_=lo,
            to=hi,
            variable=var,
            orient=tk.HORIZONTAL,
            command=lambda _v: self._on_banks_change(),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        value = tk.Label(
            row,
            text="—",
            width=10,
            bg=ACCENT,
            fg="#0d0d0d",
            font=("Menlo", 13, "bold"),
            padx=8,
            pady=3,
        )
        value.pack(side=tk.RIGHT)
        return value

    def _toggle_banks(self) -> None:
        self._banks_expanded = not self._banks_expanded
        if self._banks_expanded:
            self.banks_header.configure(text="▾ 6. Banks")
            self.banks_body.pack(fill=tk.X, after=self.banks_header)
            self.update_idletasks()
            self._on_inner_configure()
            bbox = self.canvas.bbox("all")
            if bbox and bbox[3] > 0:
                inner = self.nametowidget(self.canvas.itemcget(self._canvas_win, "window"))
                y = self.banks_header.winfo_rooty() - inner.winfo_rooty()
                self.canvas.yview_moveto(max(0.0, min(1.0, y / bbox[3])))
        else:
            self.banks_header.configure(text="▸ 6. Banks")
            self.banks_body.pack_forget()
            self.update_idletasks()
            self._on_inner_configure()

    def _read_banks_from_ui(self) -> list[BankParams]:
        banks: list[BankParams] = []
        for w in self._bank_widgets:
            lo = pos_to_hz(float(w["lo"].get()))
            hi = pos_to_hz(float(w["hi"].get()))
            if hi <= lo:
                hi = min(10000.0, lo + 10.0)
            banks.append(
                BankParams(
                    index=int(w["index"]),
                    enabled=bool(w["enabled"].get()),
                    name=w["name"].get(),
                    lo_hz=lo,
                    hi_hz=hi,
                    threshold=float(w["thr"].get()),
                ).clamped()
            )
        return banks

    def _load_banks_into_ui(self, banks: list[BankParams]) -> None:
        self._banks_applying = True
        by_i = {b.index: b.clamped() for b in banks}
        for w in self._bank_widgets:
            b = by_i[int(w["index"])]
            w["enabled"].set(b.enabled)
            w["name"].set(b.name)
            w["lo"].set(hz_to_pos(b.lo_hz))
            w["hi"].set(hz_to_pos(b.hi_hz))
            w["thr"].set(b.threshold)
            self._refresh_bank_labels(w)
        self._banks_applying = False

    def _refresh_bank_labels(self, w: dict) -> None:
        lo = pos_to_hz(float(w["lo"].get()))
        hi = pos_to_hz(float(w["hi"].get()))
        thr = float(w["thr"].get())
        w["lo_lbl"].configure(text=f"{lo:.0f} Hz")
        w["hi_lbl"].configure(text=f"{hi:.0f} Hz")
        w["thr_lbl"].configure(text=f"{thr:.2f}")
        if hi <= lo:
            w["err"].configure(text="Low ≥ High")
        else:
            w["err"].configure(text="")

    def _on_banks_change(self) -> None:
        if self._banks_applying:
            return
        for w in self._bank_widgets:
            self._refresh_bank_labels(w)
        self.engine.apply_banks(self._read_banks_from_ui())

    def _apply_bank_preset(self, name: str) -> None:
        banks = BANK_PRESETS[name]
        self._load_banks_into_ui(banks)
        self.engine.apply_banks(banks)

    def _toggle_tune(self) -> None:
        self._tune_expanded = not self._tune_expanded
        if self._tune_expanded:
            self.tune_header.configure(text="▾ 5. Tune")
            self.tune_body.pack(fill=tk.X, after=self.tune_header)
            self.update_idletasks()
            self._on_inner_configure()
            bbox = self.canvas.bbox("all")
            if bbox and bbox[3] > 0:
                inner = self.nametowidget(self.canvas.itemcget(self._canvas_win, "window"))
                y = self.tune_header.winfo_rooty() - inner.winfo_rooty()
                self.canvas.yview_moveto(max(0.0, min(1.0, y / bbox[3])))
        else:
            self.tune_header.configure(text="▸ 5. Tune")
            self.tune_body.pack_forget()
            self.update_idletasks()
            self._on_inner_configure()

    def _load_tune_into_sliders(self, tune: TuneParams) -> None:
        self._tune_applying = True
        t = tune.clamped()
        mapping = {
            "threshold": t.threshold,
            "amount": t.amount,
            "attack_s": t.attack_s,
            "release_s": t.release_s,
            "makeup": t.makeup,
            "sensitivity": t.sensitivity,
            "hold_ms": t.hold_ms,
            "kick_strictness": t.kick_strictness,
        }
        for key, val in mapping.items():
            var, lbl = self._sliders[key]
            var.set(val)
            lbl.configure(text=self._fmt_slider(key, val))
        self._tune_applying = False

    @staticmethod
    def _fmt_slider(key: str, val: float) -> str:
        if key in ("attack_s", "release_s", "threshold"):
            return f"{val:.3f}"
        if key == "hold_ms":
            return f"{val:.0f}"
        return f"{val:.2f}"

    def _read_tune_from_sliders(self) -> TuneParams:
        g = {k: float(var.get()) for k, (var, _) in self._sliders.items()}
        return TuneParams(
            threshold=g["threshold"],
            amount=g["amount"],
            attack_s=g["attack_s"],
            release_s=g["release_s"],
            makeup=g["makeup"],
            sensitivity=g["sensitivity"],
            hold_ms=g["hold_ms"],
            kick_strictness=g["kick_strictness"],
        ).clamped()

    def _on_tune_change(self, key: str) -> None:
        if self._tune_applying:
            return
        var, lbl = self._sliders[key]
        val = float(var.get())
        lbl.configure(text=self._fmt_slider(key, val))
        self.engine.apply_tune(self._read_tune_from_sliders())

    def _apply_preset(self, name: str) -> None:
        tune = PRESETS[name]
        self._load_tune_into_sliders(tune)
        self.engine.apply_tune(tune)

    def _toggle_mute(self) -> None:
        self.engine.set_mute(not self.engine.mute)
        self._refresh_mute_ui()

    def _refresh_mute_ui(self) -> None:
        if self.engine.mute:
            self.mute_btn.configure(text="MUTED", style="MuteOn.TButton")
        else:
            self.mute_btn.configure(text="Mute", style="MuteOff.TButton")
        if self.mode_var.get() == "Live":
            self.mute_hint.configure(text="(no monitor in Live)")
        else:
            self.mute_hint.configure(text="")

    def _on_mode(self) -> None:
        if self.mode_var.get() == "File":
            self.live_frame.pack_forget()
            self.file_frame.pack(fill=tk.X, pady=(8, 0))
            self.hint_var.set("Select a file to enable Start.")
        else:
            self.file_frame.pack_forget()
            self.live_frame.pack(fill=tk.X, pady=(8, 0))
            self.hint_var.set("Select an input device to enable Start.")
            if self.engine.snapshot().get("status") == "running":
                self.engine.stop()
        self._refresh_mute_ui()
        self._update_start_enabled()

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Audio file",
            filetypes=[
                ("Audio", "*.wav *.mp3 *.flac *.ogg *.aiff *.aif *.m4a"),
                ("All", "*.*"),
            ],
        )
        if path:
            self._file_path = path
            self.file_var.set(path)
            self._update_start_enabled()

    def _refresh_audio_devices(self) -> None:
        devices = list_input_devices()
        labels = [label for _, label in devices] or ["(no input devices)"]
        self.device_combo["values"] = labels
        if labels and (not self.device_var.get() or self.device_var.get() not in labels):
            self.device_var.set(labels[0])

    def _refresh_ports(self) -> None:
        self._refresh_audio_devices()
        midis = list_midi_output_names()
        self.midi_combo["values"] = midis
        if midis and self.midi_port.get() not in midis:
            self.midi_port.set(midis[0])
        self._update_start_enabled()

    def _parse_device(self) -> int | None:
        label = self.device_var.get()
        if not label or label.startswith("("):
            return None
        try:
            return int(label.split(":", 1)[0].strip())
        except ValueError:
            return None

    def _source_ok(self) -> bool:
        if self.mode_var.get() == "File":
            return bool(self._file_path and Path(self._file_path).is_file())
        return self._parse_device() is not None

    def _update_start_enabled(self) -> None:
        snap = self.engine.snapshot()
        running = snap.get("status") == "running"
        ok = self._source_ok()
        self.start_btn.configure(state=tk.NORMAL if (ok and not running) else tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        if not ok:
            if self.mode_var.get() == "File":
                self.hint_var.set("Select a file to enable Start.")
            else:
                self.hint_var.set("Select an input device to enable Start.")
        elif "Ignore" not in (self.hint_var.get() or "") and "How " not in (self.hint_var.get() or "") and "More" not in (self.hint_var.get() or "") and "Min time" not in (self.hint_var.get() or "") and "Reject" not in (self.hint_var.get() or "") and "Boost" not in (self.hint_var.get() or ""):
            self.hint_var.set("")

    def _configure_engine_outputs(self) -> None:
        try:
            port = int(float(self.osc_port.get()))
        except ValueError:
            port = config.OSC_PORT
        self.engine.configure_outputs(
            osc_enabled=bool(self.osc_enabled.get()),
            osc_host=self.osc_host.get().strip() or config.OSC_HOST,
            osc_port=port,
            midi_enabled=bool(self.midi_enabled.get()),
            midi_port=self.midi_port.get().strip() or config.MIDI_PORT_NAME,
        )

    def _start(self) -> None:
        if not self._source_ok():
            return
        self._configure_engine_outputs()
        self.engine.apply_tune(self._read_tune_from_sliders())
        self.engine.apply_banks(self._read_banks_from_ui())
        if self.mode_var.get() == "File":
            assert self._file_path
            self.engine.start_file(self._file_path)
        else:
            self.engine.start_live(self._parse_device())
        self._update_start_enabled()

    def _stop(self) -> None:
        self.engine.stop()
        self._update_start_enabled()

    def _poll(self) -> None:
        snap = self.engine.snapshot()
        status = snap.get("status") or "idle"
        err = snap.get("error") or ""
        self.status_var.set(status)
        self.error_var.set(err)
        color = {"idle": MUTED_FG, "running": ACCENT, "error": ERROR, "starting": "#6bcfff"}.get(
            status, MUTED_FG
        )
        self.status_lbl.configure(fg=color)

        flash = snap.get("flash") or {}
        for name, lbl in self._trig_labels.items():
            on = float(flash.get(name, 0.0)) > 0.5
            lbl.configure(bg=ACCENT if on else BAR_BG, fg=("#0d0d0d" if on else MUTED_FG))

        floats = snap.get("floats") or {}
        for name, fill in self._meter_fills.items():
            val = float(floats.get(name, 0.0))
            if name == "bpm":
                pct = max(
                    0.0,
                    min(1.0, (val - config.BPM_MIN) / (config.BPM_MAX - config.BPM_MIN)),
                )
                self._meter_labels[name].configure(text=f"{name}: {val:.1f}")
            else:
                pct = max(0.0, min(1.0, val))
                self._meter_labels[name].configure(text=f"{name}: {val:.2f}")
            track = fill._track  # type: ignore[attr-defined]
            track.update_idletasks()
            w = max(1, int(track.winfo_width() * pct))
            fill.place(x=0, y=0, relheight=1.0, width=w)

        for w in self._bank_widgets:
            key = f"bank{w['index']}"
            on = float(flash.get(key, 0.0)) > 0.5
            w["flash"].configure(bg=ACCENT if on else BAR_BG, fg=("#0d0d0d" if on else MUTED_FG))
            val = float(floats.get(key, 0.0))
            fill = w["fill"]
            track = fill._track  # type: ignore[attr-defined]
            track.update_idletasks()
            bw = max(1, int(track.winfo_width() * max(0.0, min(1.0, val))))
            fill.place(x=0, y=0, relheight=1.0, width=bw)

        self._draw_scope()
        self._update_start_enabled()
        self.after(UI_POLL_MS, self._poll)

    @staticmethod
    def _scope_tick_name(channel: str) -> str | None:
        if channel == "onset_strength":
            return "onset"
        if channel == "bass_energy":
            return "kick"
        if channel in BANK_IDS:
            return channel
        return None

    def _draw_scope(self) -> None:
        cv = self.scope_canvas
        w = max(int(cv.winfo_width()), 2)
        h = max(int(cv.winfo_height()), 2)
        cv.delete("all")
        pad = 4
        mid_y = h / 2.0
        cv.create_line(pad, mid_y, w - pad, mid_y, fill="#2a2a2a")
        channel = self.scope_channel.get() or config.SCOPE_DEFAULT_CHANNEL
        samples = self.engine.scope_samples(config.SCOPE_WINDOW_S)
        inner_w = max(1.0, w - 2 * pad)
        inner_h = max(1.0, h - 2 * pad)
        tick = self._scope_tick_name(channel)

        if channel.startswith("bank"):
            try:
                idx = int(channel[-1])
                bank = next(b for b in self.engine.get_banks() if b.index == idx)
                thr_y = pad + inner_h * (1.0 - max(0.0, min(1.0, bank.threshold)))
                cv.create_line(pad, thr_y, w - pad, thr_y, fill=MUTED_FG, dash=(3, 3))
            except (StopIteration, ValueError):
                pass

        if len(samples) < 2:
            return

        n = len(samples)
        pts: list[float] = []
        for i, (_t, floats, bangs) in enumerate(samples):
            x = pad + inner_w * (i / (n - 1))
            val = max(0.0, min(1.0, float(floats.get(channel, 0.0))))
            y = pad + inner_h * (1.0 - val)
            pts.extend((x, y))
            if tick and bangs.get(tick):
                base = pad + inner_h
                cv.create_line(x, base, x, base - 8, fill=ACCENT, width=2)
        cv.create_line(*pts, fill=ACCENT, width=2, smooth=True)

    def _on_close(self) -> None:
        self._unbind_mousewheel()
        try:
            self.engine.stop()
        except Exception:
            pass
        self.destroy()


def launch() -> None:
    app = MusicAnalyseApp()
    app.mainloop()
