"""
FocusLensApp  –  main tkinter GUI.

Layout:
  - header bar (logo + session timer + controls)
  - main body:
      - left: camera feed (with bbox overlay)
      - right: state card, stats cards (3), timeline strip
  - status bar
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import queue
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from config import *
from core import CameraThread, FaceDetector, SessionLogger


# tiny helper widgets

def _label(parent, text="", fg=COL_TEXT, bg=COL_SURFACE, font=("Segoe UI", 10),
           anchor="w", **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg, font=font, anchor=anchor, **kw)


def _frame(parent, bg=COL_SURFACE, **kw):
    return tk.Frame(parent, bg=bg, **kw)


def _sep(parent, bg=COL_BORDER):
    return tk.Frame(parent, bg=bg, height=1)


class RoundedCard(tk.Canvas):
    """A canvas that draws itself as a rounded-rect card."""

    def __init__(self, parent, radius=10, bg_fill=COL_SURFACE,
                 border_col=COL_BORDER, **kw):
        super().__init__(parent, bg=COL_BG, highlightthickness=0, **kw)
        self._r = radius
        self._fill = bg_fill
        self._border = border_col
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _=None):
        self.delete("bg")
        w, h = self.winfo_width(), self.winfo_height()
        r = self._r
        self.create_polygon(
            r, 0, w-r, 0, w, r, w, h-r, w-r, h, r, h, 0, h-r, 0, r,
            smooth=True, fill=self._fill, outline=self._border,
            width=1, tags="bg"
        )
        self.tag_lower("bg")


# Timeline canvas

class TimelineCanvas(tk.Canvas):
    """Draws the horizontal focus-state timeline strip."""

    SEG_H = 18
    PADDING = 4

    def __init__(self, parent, **kw):
        kw.pop('bg', None)
        super().__init__(parent, bg=COL_SURFACE, highlightthickness=0,
                        height=self.SEG_H + self.PADDING * 2, **kw)
        self._segments: list[str] = []   # list of state strings
        self.bind("<Configure>", self._redraw)

    def push(self, state: str):
        self._segments.append(state)
        if len(self._segments) > 600:      # keep ~10 min at 1/s
            self._segments.pop(0)
        self._redraw()

    def clear(self):
        self._segments = []
        self._redraw()

    def _redraw(self, _=None):
        self.delete("all")
        w = self.winfo_width()
        if w < 4 or not self._segments:
            return
        n = len(self._segments)
        seg_w = max(2, w / n)
        p = self.PADDING
        for i, state in enumerate(self._segments):
            x0 = p + i * seg_w
            x1 = x0 + seg_w - 1
            col = STATE_COLOURS.get(state, COL_MUTED)
            self.create_rectangle(x0, p, x1, p + self.SEG_H,
                                  fill=col, outline="", width=0)


# Stat card

class StatCard(tk.Frame):
    def __init__(self, parent, label: str, value: str = "—",
                 value_col: str = COL_TEXT, **kw):
        super().__init__(parent, bg=COL_SURFACE, **kw)

        _label(self, text=label, fg=COL_MUTED, bg=COL_SURFACE,
               font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(10, 0))

        self._val_var = tk.StringVar(value=value)
        self._val_lbl = tk.Label(self, textvariable=self._val_var,
                                 fg=value_col, bg=COL_SURFACE,
                                 font=("Consolas", 22, "bold"), anchor="w")
        self._val_lbl.pack(anchor="w", padx=12, pady=(2, 10))

    def set(self, value: str, col: str | None = None):
        self._val_var.set(value)
        if col:
            self._val_lbl.config(fg=col)


# Main application

class FocusLensApp:

    def __init__(self):
        self.root = tk.Tk()
        self._configure_root()

        # core modules
        self._camera   = CameraThread()
        self._detector = FaceDetector()
        self._logger   = SessionLogger()

        # state
        self._session_active = False
        self._current_state  = "idle"
        self._last_log_t     = 0.0
        self._fps_display    = 0

        self._build_ui()

    # window setup

    def _configure_root(self):
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=COL_BG)
        self.root.resizable(True, True)
        self.root.minsize(820, 540)
        # attempt to set a dark title bar on Windows 11
        try:
            from ctypes import windll, byref, sizeof, c_int
            HWND = windll.user32.GetParent(self.root.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(HWND, 20, byref(c_int(1)), sizeof(c_int))
        except Exception:
            pass

    # UI construction

    def _build_ui(self):
        self._build_header()
        _sep(self.root, bg=COL_BORDER).pack(fill="x")
        self._build_body()
        self._build_statusbar()

    def _build_header(self):
        hdr = _frame(self.root, bg=COL_BG)
        hdr.pack(fill="x", padx=16, pady=(12, 8))

        # logo
        logo_f = _frame(hdr, bg=COL_BG)
        logo_f.pack(side="left")
        tk.Canvas(logo_f, width=10, height=10, bg=COL_BG,
                  highlightthickness=0).pack(side="left", padx=(0, 8))
        self._logo_dot = tk.Canvas(logo_f, width=10, height=10,
                                   bg=COL_BG, highlightthickness=0)
        self._logo_dot.pack(side="left", padx=(0, 8))
        self._logo_dot_id = self._logo_dot.create_oval(1, 1, 9, 9,
                                                        fill=COL_MUTED, outline="")

        _label(logo_f, text="FOCUSLENS", fg=COL_TEXT, bg=COL_BG,
               font=("Consolas", 13, "bold")).pack(side="left")

        stg = _label(logo_f, text="  STAGE 1", fg=COL_MUTED, bg=COL_BG,
                     font=("Consolas", 9))
        stg.pack(side="left", padx=(6, 0))

        # timer
        timer_f = _frame(hdr, bg=COL_BG)
        timer_f.pack(side="left", padx=32)
        _label(timer_f, text="SESSION", fg=COL_MUTED, bg=COL_BG,
               font=("Segoe UI", 7)).pack(anchor="w")
        self._timer_var = tk.StringVar(value="00:00:00")
        tk.Label(timer_f, textvariable=self._timer_var,
                 fg=COL_ACCENT, bg=COL_BG,
                 font=("Consolas", 18, "bold")).pack(anchor="w")

        # controls
        ctrl_f = _frame(hdr, bg=COL_BG)
        ctrl_f.pack(side="right")

        self._btn_start = tk.Button(
            ctrl_f, text="▶  START SESSION",
            fg="#0d0f12", bg=COL_ACCENT,
            activebackground=COL_ACCENT, activeforeground="#0d0f12",
            font=("Consolas", 10, "bold"),
            relief="flat", bd=0, padx=16, pady=7,
            cursor="hand2", command=self._start_session
        )
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_stop = tk.Button(
            ctrl_f, text="■  STOP",
            fg=COL_MUTED, bg=COL_BORDER,
            activebackground="#2a2f38", activeforeground=COL_TEXT,
            font=("Consolas", 10, "bold"),
            relief="flat", bd=0, padx=16, pady=7,
            cursor="hand2", command=self._stop_session,
            state="disabled"
        )
        self._btn_stop.pack(side="left")

    def _build_body(self):
        body = _frame(self.root, bg=COL_BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=0, minsize=280)
        body.grid_rowconfigure(0, weight=1)

        self._build_camera_panel(body)
        self._build_right_panel(body)

    def _build_camera_panel(self, parent):
        cam_outer = _frame(parent, bg=COL_BORDER)
        cam_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cam_outer.grid_rowconfigure(0, weight=1)
        cam_outer.grid_columnconfigure(0, weight=1)

        cam_inner = _frame(cam_outer, bg=COL_SURFACE)
        cam_inner.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        cam_inner.grid_rowconfigure(0, weight=1)
        cam_inner.grid_columnconfigure(0, weight=1)

        # video canvas
        self._cam_canvas = tk.Canvas(cam_inner, bg="#07090c",
                                     highlightthickness=0)
        self._cam_canvas.grid(row=0, column=0, sticky="nsew")

        # placeholder text shown before session starts
        self._cam_placeholder = self._cam_canvas.create_text(
            320, 240, text="⏸  camera inactive\n\npress START SESSION",
            fill=COL_MUTED, font=("Segoe UI", 13), justify="center"
        )

        # bottom strip: status + FPS
        strip = _frame(cam_inner, bg=COL_SURFACE)
        strip.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        self._cam_status_dot = tk.Canvas(strip, width=8, height=8,
                                         bg=COL_SURFACE, highlightthickness=0)
        self._cam_status_dot.pack(side="left", padx=(10, 4), pady=6)
        self._cam_dot_id = self._cam_status_dot.create_oval(
            1, 1, 7, 7, fill=COL_MUTED, outline="")

        self._cam_status_var = tk.StringVar(value="idle")
        tk.Label(strip, textvariable=self._cam_status_var,
                 fg=COL_MUTED, bg=COL_SURFACE,
                 font=("Consolas", 9)).pack(side="left")

        self._fps_var = tk.StringVar(value="— fps")
        tk.Label(strip, textvariable=self._fps_var,
                 fg=COL_MUTED, bg=COL_SURFACE,
                 font=("Consolas", 9)).pack(side="right", padx=10)

    def _build_right_panel(self, parent):
        rp = _frame(parent, bg=COL_BG)
        rp.grid(row=0, column=1, sticky="nsew")

        # state card
        state_card = _frame(rp, bg=COL_SURFACE,
                            highlightbackground=COL_BORDER,
                            highlightthickness=1)
        state_card.pack(fill="x", pady=(0, 8))

        _label(state_card, text="DETECTED STATE", fg=COL_MUTED, bg=COL_SURFACE,
               font=("Consolas", 8)).pack(anchor="w", padx=12, pady=(10, 0))

        state_inner = _frame(state_card, bg=COL_SURFACE)
        state_inner.pack(fill="x", padx=12, pady=(6, 10))

        self._state_icon_var = tk.StringVar(value="⏸")
        tk.Label(state_inner, textvariable=self._state_icon_var,
                 fg=COL_TEXT, bg=COL_SURFACE,
                 font=("Segoe UI Emoji", 22)).pack(side="left", padx=(0, 10))

        info_f = _frame(state_inner, bg=COL_SURFACE)
        info_f.pack(side="left", fill="x", expand=True)

        self._state_name_var = tk.StringVar(value="idle")
        tk.Label(info_f, textvariable=self._state_name_var,
                 fg=COL_TEXT, bg=COL_SURFACE,
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x")

        self._state_sub_var = tk.StringVar(value="start a session to begin")
        tk.Label(info_f, textvariable=self._state_sub_var,
                 fg=COL_MUTED, bg=COL_SURFACE,
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")

        _sep(rp).pack(fill="x", pady=(0, 8))

        # stat cards
        self._card_focus   = StatCard(rp, "FOCUS SCORE",       "—", COL_TEXT)
        self._card_focused = StatCard(rp, "FOCUSED TIME",      "0s", COL_ACCENT)
        self._card_away    = StatCard(rp, "AWAY / DISTRACTED", "0s", COL_WARN)

        for c in (self._card_focus, self._card_focused, self._card_away):
            c.config(highlightbackground=COL_BORDER, highlightthickness=1)
            c.pack(fill="x", pady=(0, 6))

        _sep(rp).pack(fill="x", pady=(2, 8))

        # timeline
        _label(rp, text="FOCUS TIMELINE", fg=COL_MUTED, bg=COL_BG,
               font=("Consolas", 8)).pack(anchor="w")

        self._timeline = TimelineCanvas(rp, bg=COL_SURFACE)
        self._timeline.pack(fill="x", pady=(4, 4))

        legend_f = _frame(rp, bg=COL_BG)
        legend_f.pack(fill="x")
        for state, col in STATE_COLOURS.items():
            dot = tk.Canvas(legend_f, width=10, height=10,
                            bg=COL_BG, highlightthickness=0)
            dot.create_rectangle(1, 3, 9, 9, fill=col, outline="")
            dot.pack(side="left", padx=(0, 3))
            _label(legend_f, text=state, fg=COL_MUTED, bg=COL_BG,
                   font=("Segoe UI", 8)).pack(side="left", padx=(0, 12))

        _sep(rp).pack(fill="x", pady=(8, 0))

        # report button
        self._btn_report = tk.Button(
            rp, text="↗  Generate Report",
            fg=COL_MUTED, bg=COL_SURFACE,
            activebackground=COL_BORDER, activeforeground=COL_ACCENT,
            font=("Consolas", 10), relief="flat", bd=0,
            pady=10, cursor="hand2",
            command=self._generate_report, state="disabled"
        )
        self._btn_report.pack(fill="x", pady=(6, 0))

    def _build_statusbar(self):
        _sep(self.root, bg=COL_BORDER).pack(fill="x")
        sb = _frame(self.root, bg=COL_BG)
        sb.pack(fill="x", padx=12, pady=4)

        self._status_var = tk.StringVar(value="ready  ·  mediapipe face detection  ·  emotion model: stage 2")
        tk.Label(sb, textvariable=self._status_var,
                 fg=COL_MUTED, bg=COL_BG,
                 font=("Consolas", 8)).pack(side="left")

        self._model_var = tk.StringVar(value="⚠ emotion model not loaded")
        tk.Label(sb, textvariable=self._model_var,
                 fg=COL_WARN, bg=COL_BG,
                 font=("Consolas", 8)).pack(side="right")

    # session control

    def _start_session(self):
        if self._session_active:
            return
        self._session_active = True
        self._timeline.clear()

        # start camera thread
        self._camera = CameraThread()
        self._camera.start()

        # start logging
        sid = self._logger.start_session()

        # update UI
        self._btn_start.config(state="disabled", text="● RECORDING",
                               fg=COL_ACCENT, bg="#0d2520")
        self._btn_stop.config(state="normal")
        self._btn_report.config(state="disabled")
        self._cam_canvas.itemconfig(self._cam_placeholder, state="hidden")
        self._cam_status_dot.itemconfig(self._cam_dot_id, fill=COL_ACCENT)
        self._cam_status_var.set("live")
        self._logo_dot.itemconfig(self._logo_dot_id, fill=COL_ACCENT)
        self._state_sub_var.set("detecting…")
        self._status_var.set(f"session {sid} started  ·  logging every {LOG_INTERVAL_S}s")

        # kick off the processing loop
        self._process_loop()

    def _stop_session(self):
        if not self._session_active:
            return
        self._session_active = False
        self._camera.stop()

        summary = self._logger.end_session()

        self._btn_start.config(state="normal", text="▶  NEW SESSION",
                               fg="#0d0f12", bg=COL_ACCENT)
        self._btn_stop.config(state="disabled")
        self._btn_report.config(state="normal")
        self._cam_status_dot.itemconfig(self._cam_dot_id, fill=COL_MUTED)
        self._cam_status_var.set("stopped")
        self._logo_dot.itemconfig(self._logo_dot_id, fill=COL_MUTED)
        self._state_icon_var.set("⏸")
        self._state_name_var.set("session ended")
        self._state_sub_var.set(f"focus score: {summary.focus_pct}%  ·  generate report below")
        self._status_var.set(
            f"session saved  ·  {summary.focused_s:.0f}s focused  ·  "
            f"{summary.duration_s:.0f}s total  ·  score {summary.focus_pct}%"
        )

    # main processing loop

    def _process_loop(self):
        """Called ~30x/s via root.after(). Grabs a frame, detects, draws, logs."""
        if not self._session_active:
            return

        # check camera errors
        if self._camera.error:
            self._status_var.set(f"camera error: {self._camera.error}")
            self._stop_session()
            return

        # grab latest frame
        try:
            frame = self._camera.frame_queue.get_nowait()
        except queue.Empty:
            self.root.after(16, self._process_loop)
            return

        # face detection
        result = self._detector.detect(frame)

        # determine focus state (Stage 2 will replace this with real emotions)
        if result.face_detected:
            state = "focused"          # placeholder — Stage 2 will classify emotion
            emotion_label = "present"
        else:
            state = "away"
            emotion_label = "no_face"

        self._current_state = state

        # draw bounding box overlay
        annotated = self._draw_overlay(frame, result, state)

        # render to canvas
        self._render_frame(annotated)

        # log once per LOG_INTERVAL_S
        now = time.time()
        if now - self._last_log_t >= LOG_INTERVAL_S:
            self._logger.log(state, result.confidence, emotion_label)
            self._last_log_t = now
            self._timeline.push(state)
            self._update_stats()

        # update live UI
        self._update_state_display(state, result)
        self._fps_var.set(f"{self._camera.fps_actual:.0f} fps")

        # schedule next frame
        self.root.after(16, self._process_loop)

    # drawing

    def _draw_overlay(self, frame, result, state):
        out = frame.copy()
        col_bgr = {
            "focused":    (0, 229, 160),   # COL_ACCENT
            "distracted": (11, 158, 245),  # COL_WARN in BGR
            "away":       (68, 68, 68),
        }.get(state, (68, 68, 68))

        if result.face_detected and result.bbox:
            x, y, w, h = result.bbox
            # corner brackets instead of a plain rectangle — looks cleaner
            corner = 18
            thick  = 2
            pts = [
                ((x, y), (x+corner, y), (x, y+corner)),
                ((x+w, y), (x+w-corner, y), (x+w, y+corner)),
                ((x, y+h), (x+corner, y+h), (x, y+h-corner)),
                ((x+w, y+h), (x+w-corner, y+h), (x+w, y+h-corner)),
            ]
            for corner_pts in pts:
                cv2.line(out, corner_pts[0], corner_pts[1], col_bgr, thick, cv2.LINE_AA)
                cv2.line(out, corner_pts[0], corner_pts[2], col_bgr, thick, cv2.LINE_AA)

            # confidence badge
            badge = f"{result.confidence:.0%}"
            cv2.putText(out, badge, (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col_bgr, 1, cv2.LINE_AA)

        # tiny state indicator bottom-left
        state_txt = state.upper()
        cv2.putText(out, state_txt, (10, out.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col_bgr, 1, cv2.LINE_AA)
        return out

    def _render_frame(self, frame_bgr):
        """Convert OpenCV BGR frame to tkinter PhotoImage and display it."""
        if not _PIL_OK:
            return
        cw = self._cam_canvas.winfo_width()
        ch = self._cam_canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        h, w = frame_bgr.shape[:2]
        scale = min(cw / w, ch / h)
        nw, nh = int(w * scale), int(h * scale)

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb).resize((nw, nh), Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(img)

        self._cam_canvas.delete("frame")
        ox = (cw - nw) // 2
        oy = (ch - nh) // 2
        self._cam_canvas.create_image(ox, oy, anchor="nw",
                                       image=self._photo, tags="frame")

    # live stats update

    def _update_state_display(self, state, result):
        icon = STATE_ICONS.get(state, "⏸")
        self._state_icon_var.set(icon)
        self._state_name_var.set(state)
        col = STATE_COLOURS.get(state, COL_MUTED)
        if result.face_detected:
            self._state_sub_var.set(f"face confidence: {result.confidence:.0%}  ·  emotion model: stage 2")
        else:
            self._state_sub_var.set("no face detected")

    def _update_stats(self):
        stats = self._logger.live_stats()
        elapsed = stats["elapsed_s"]
        focused_s = elapsed * (stats["focused_pct"] / 100)
        away_s    = elapsed * ((stats["distracted_pct"] + stats["away_pct"]) / 100)

        pct = stats["focused_pct"]
        col = COL_ACCENT if pct >= 70 else COL_WARN if pct >= 40 else COL_DANGER
        self._card_focus.set(f"{pct:.0f}%", col)
        self._card_focused.set(self._fmt_s(focused_s), COL_ACCENT)
        self._card_away.set(self._fmt_s(away_s), COL_WARN)

        elapsed_str = self._fmt_s(elapsed)
        self._timer_var.set(self._fmt_hms(elapsed))

    @staticmethod
    def _fmt_s(seconds: float) -> str:
        s = int(seconds)
        if s < 60:    return f"{s}s"
        if s < 3600:  return f"{s//60}m {s%60:02d}s"
        return f"{s//3600}h {(s%3600)//60:02d}m"

    @staticmethod
    def _fmt_hms(seconds: float) -> str:
        s = int(seconds)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    # report

    def _generate_report(self):
        """Placeholder — Stage 5 builds the real PDF/HTML report."""
        import subprocess, sys
        sessions_path = Path(SESSIONS_DIR)
        if sys.platform == "win32":
            subprocess.Popen(f'explorer "{sessions_path.resolve()}"')
        self._status_var.set("report generator coming in Stage 5  ·  raw data saved to sessions/")

    # run

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self._session_active:
            self._stop_session()
        self._camera.stop()
        self._detector.close()
        self.root.destroy()
