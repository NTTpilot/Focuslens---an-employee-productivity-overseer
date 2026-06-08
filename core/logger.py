"""
SessionLogger  –  records timestamped focus-state snapshots to disk.

Each session creates:
  sessions/<ISO-timestamp>/log.csv      – raw per-second log
  sessions/<ISO-timestamp>/summary.json – computed at session end
"""

import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List

from config import SESSIONS_DIR, STATE_COLOURS


@dataclass
class Snapshot:
    timestamp: float        # unix epoch
    elapsed_s: float        # seconds since session start
    state: str              # focused | distracted | away
    face_confidence: float
    emotion: str            # raw emotion label (Stage 2+)


@dataclass
class SessionSummary:
    session_id: str
    start_iso: str
    end_iso: str
    duration_s: float
    total_snapshots: int
    focused_s: float
    distracted_s: float
    away_s: float
    focus_pct: float
    productive_hours: float
    total_hours: float
    timeline: List[dict]    # [{t, state}, …] – for report chart


class SessionLogger:

    def __init__(self):
        self._session_id: str | None = None
        self._session_dir: Path | None = None
        self._start_time: float | None = None
        self._snapshots: List[Snapshot] = []
        self._csv_file = None
        self._csv_writer = None
        self._last_log_t: float = 0.0

    # lifecycle

    def start_session(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_id = ts
        self._session_dir = Path(SESSIONS_DIR) / ts
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._start_time = time.time()
        self._snapshots = []
        self._last_log_t = self._start_time

        log_path = self._session_dir / "log.csv"
        self._csv_file = open(log_path, "w", newline="", encoding="utf-8")
        self._csv_writer = csv.DictWriter(
            self._csv_file,
            fieldnames=["timestamp", "elapsed_s", "state", "face_confidence", "emotion"]
        )
        self._csv_writer.writeheader()

        return self._session_id

    def log(self, state: str, face_confidence: float = 0.0, emotion: str = "unknown"):
        """Call this once per second while a session is active."""
        if self._start_time is None:
            return

        now = time.time()
        snap = Snapshot(
            timestamp=now,
            elapsed_s=round(now - self._start_time, 2),
            state=state,
            face_confidence=round(face_confidence, 3),
            emotion=emotion,
        )
        self._snapshots.append(snap)
        self._csv_writer.writerow(asdict(snap))
        self._csv_file.flush()

    def end_session(self) -> SessionSummary:
        if self._csv_file:
            self._csv_file.close()

        summary = self._build_summary()

        # write summary.json
        summary_path = self._session_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(asdict(summary), f, indent=2)

        # reset state
        self._session_id = None
        self._start_time = None
        return summary

    @property
    def active(self) -> bool:
        return self._start_time is not None

    @property
    def elapsed_s(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    # summary builder

    def _build_summary(self) -> SessionSummary:
        total   = len(self._snapshots)
        focused = sum(1 for s in self._snapshots if s.state == "focused")
        dist    = sum(1 for s in self._snapshots if s.state == "distracted")
        away    = sum(1 for s in self._snapshots if s.state == "away")

        dur = self._snapshots[-1].elapsed_s if self._snapshots else 0.0
        focus_pct = (focused / total * 100) if total else 0.0

        start_dt = datetime.fromtimestamp(self._snapshots[0].timestamp) if self._snapshots else datetime.now()
        end_dt   = datetime.fromtimestamp(self._snapshots[-1].timestamp) if self._snapshots else datetime.now()

        timeline = [{"t": s.elapsed_s, "state": s.state} for s in self._snapshots]

        return SessionSummary(
            session_id=self._session_id or "unknown",
            start_iso=start_dt.isoformat(),
            end_iso=end_dt.isoformat(),
            duration_s=round(dur, 1),
            total_snapshots=total,
            focused_s=float(focused),
            distracted_s=float(dist),
            away_s=float(away),
            focus_pct=round(focus_pct, 1),
            productive_hours=round(focused / 3600, 3),
            total_hours=round(dur / 3600, 3),
            timeline=timeline,
        )

    # live stats (for GUI display)

    def live_stats(self) -> dict:
        total   = len(self._snapshots)
        if total == 0:
            return {"focused_pct": 0, "distracted_pct": 0, "away_pct": 0, "elapsed_s": 0}
        focused = sum(1 for s in self._snapshots if s.state == "focused")
        dist    = sum(1 for s in self._snapshots if s.state == "distracted")
        away    = sum(1 for s in self._snapshots if s.state == "away")
        return {
            "focused_pct":    round(focused / total * 100, 1),
            "distracted_pct": round(dist    / total * 100, 1),
            "away_pct":       round(away    / total * 100, 1),
            "elapsed_s":      self.elapsed_s,
        }
