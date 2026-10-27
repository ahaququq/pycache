"""Live tracker for downloads and serves.

Provides real-time event streaming via Server-Sent Events (SSE).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Callable

from .db import db

log = logging.getLogger("tracker")


class EventType(Enum):
    DOWNLOAD_START = "download_start"
    DOWNLOAD_REDIRECT = "download_redirect"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETE = "download_complete"
    DOWNLOAD_ERROR = "download_error"
    SERVE_START = "serve_start"
    SERVE_COMPLETE = "serve_complete"
    SERVE_ERROR = "serve_error"
    PROBE_START = "probe_start"
    PROBE_COMPLETE = "probe_complete"


@dataclass
class TrackerEvent:
    """A single tracker event."""
    id: int
    timestamp: str
    event_type: str
    message: str
    details: dict
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "message": self.message,
            "details": self.details,
        }
    
    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        data = json.dumps(self.to_dict())
        return f"data: {data}\n\n"


class LiveTracker:
    """Thread-safe live tracker with SSE support."""
    
    def __init__(self, max_events: int = 500):
        self.max_events = max_events
        self._events: deque[TrackerEvent] = deque(maxlen=max_events)
        self._lock = threading.RLock()
        self._subscribers: set[Callable[[TrackerEvent], None]] = set()
        self._event_id = 0
    
    def _add_event(self, event_type: EventType, message: str, details: dict) -> TrackerEvent:
        """Add an event and notify subscribers."""
        with self._lock:
            self._event_id += 1
            event = TrackerEvent(
                id=self._event_id,
                timestamp=datetime.now().isoformat(timespec='seconds'),
                event_type=event_type.value,
                message=message,
                details=details,
            )
            self._events.append(event)
        
        # Notify subscribers
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception as exc:
                log.warning("Tracker subscriber callback failed: %s", exc)
        
        return event
    
    def subscribe(self, callback: Callable[[TrackerEvent], None]) -> None:
        """Subscribe to real-time events."""
        with self._lock:
            self._subscribers.add(callback)
    
    def unsubscribe(self, callback: Callable[[TrackerEvent], None]) -> None:
        """Unsubscribe from real-time events."""
        with self._lock:
            self._subscribers.discard(callback)
    
    def get_events(self, limit: int = 100, event_types: Optional[list[str]] = None) -> list[TrackerEvent]:
        """Get recent events, optionally filtered by type."""
        with self._lock:
            events = list(self._events)
        
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        return events[-limit:]
    
    def get_event_counts(self) -> dict[str, int]:
        """Get counts of events by type."""
        with self._lock:
            events = list(self._events)
        
        counts = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        
        return counts
    
    # --- Convenience methods for common events ---
    
    def download_start(self, local_path: str, remote_url: str, source_name: str) -> TrackerEvent:
        return self._add_event(
            EventType.DOWNLOAD_START,
            f"Starting download: {local_path}",
            {
                "local_path": local_path,
                "remote_url": remote_url,
                "source_name": source_name,
            }
        )
    
    def download_redirect(self, local_path: str, from_url: str, to_url: str) -> TrackerEvent:
        return self._add_event(
            EventType.DOWNLOAD_REDIRECT,
            f"Redirect: {from_url} → {to_url}",
            {
                "local_path": local_path,
                "from_url": from_url,
                "to_url": to_url,
            }
        )
    
    def download_progress(self, local_path: str, bytes_downloaded: int, 
                          total_bytes: Optional[int], speed_bps: float) -> TrackerEvent:
        pct = (bytes_downloaded / total_bytes * 100) if total_bytes else 0
        speed_mb = speed_bps / (1024 * 1024)
        return self._add_event(
            EventType.DOWNLOAD_PROGRESS,
            f"Downloading {local_path}: {bytes_downloaded:,} / {total_bytes or '?'} bytes ({pct:.1f}%) @ {speed_mb:.2f} MB/s",
            {
                "local_path": local_path,
                "bytes_downloaded": bytes_downloaded,
                "total_bytes": total_bytes,
                "speed_bps": speed_bps,
                "speed_mbps": speed_mb,
                "progress_pct": pct,
            }
        )
    
    def download_complete(self, local_path: str, bytes_downloaded: int, 
                          duration_s: float, cache_path: str, source_name: str) -> TrackerEvent:
        speed_mb = (bytes_downloaded / duration_s) / (1024 * 1024) if duration_s > 0 else 0
        return self._add_event(
            EventType.DOWNLOAD_COMPLETE,
            f"Downloaded {local_path} ({bytes_downloaded:,} bytes in {duration_s:.1f}s, {speed_mb:.2f} MB/s) → cached",
            {
                "local_path": local_path,
                "bytes_downloaded": bytes_downloaded,
                "duration_s": duration_s,
                "speed_mbps": speed_mb,
                "cache_path": cache_path,
                "source_name": source_name,
            }
        )
    
    def download_error(self, local_path: str, error: str, remote_url: str) -> TrackerEvent:
        return self._add_event(
            EventType.DOWNLOAD_ERROR,
            f"Download failed: {local_path} - {error}",
            {
                "local_path": local_path,
                "error": error,
                "remote_url": remote_url,
            }
        )
    
    def serve_start(self, local_path: str, remote_url: str, source_name: str, client_ip: str) -> TrackerEvent:
        return self._add_event(
            EventType.SERVE_START,
            f"Serving {local_path} to {client_ip} (source: {source_name})",
            {
                "local_path": local_path,
                "remote_url": remote_url,
                "source_name": source_name,
                "client_ip": client_ip,
            }
        )
    
    def serve_complete(self, local_path: str, bytes_sent: int, duration_s: float, 
                       client_ip: str, from_cache: bool) -> TrackerEvent:
        speed_mb = (bytes_sent / duration_s) / (1024 * 1024) if duration_s > 0 else 0
        source = "cache" if from_cache else "upstream"
        return self._add_event(
            EventType.SERVE_COMPLETE,
            f"Served {local_path} ({bytes_sent:,} bytes in {duration_s:.1f}s, {speed_mb:.2f} MB/s) from {source} to {client_ip}",
            {
                "local_path": local_path,
                "bytes_sent": bytes_sent,
                "duration_s": duration_s,
                "speed_mbps": speed_mb,
                "client_ip": client_ip,
                "from_cache": from_cache,
            }
        )
    
    def serve_error(self, local_path: str, error: str, client_ip: str) -> TrackerEvent:
        return self._add_event(
            EventType.SERVE_ERROR,
            f"Serve failed: {local_path} for {client_ip} - {error}",
            {
                "local_path": local_path,
                "error": error,
                "client_ip": client_ip,
            }
        )
    
    def probe_start(self, local_path: str, remote_url: str) -> TrackerEvent:
        return self._add_event(
            EventType.PROBE_START,
            f"Probing upstream: {local_path}",
            {
                "local_path": local_path,
                "remote_url": remote_url,
            }
        )
    
    def probe_complete(self, local_path: str, exists: bool, size: Optional[int], 
                       final_url: str, duration_s: float) -> TrackerEvent:
        status = "found" if exists else "not found"
        size_str = f"{size:,} bytes" if size else "unknown size"
        return self._add_event(
            EventType.PROBE_COMPLETE,
            f"Probe {local_path}: {status} ({size_str}, {duration_s:.2f}s) → {final_url}",
            {
                "local_path": local_path,
                "exists": exists,
                "size": size,
                "final_url": final_url,
                "duration_s": duration_s,
            }
        )


# Global tracker instance
tracker = LiveTracker()


def get_tracker() -> LiveTracker:
    return tracker