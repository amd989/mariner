"""Print task history backing SDCP commands 320 and 321.

Mariner itself keeps no record of past prints, so the provider observes them:
a task opens when a print starts and closes when the printer goes idle. The
store is persisted as JSON so history survives a restart, and bounded so it
cannot grow without limit.
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger: logging.Logger = logging.getLogger(__name__)


class TaskStatus:
    """``TaskStatus`` values from the spec."""

    OTHER = 0
    COMPLETED = 1
    EXCEPTION = 2
    STOPPED = 3


class TimeLapseStatus:
    NOT_SHOT = 0


@dataclass
class TaskRecord:
    task_id: str
    filename: str
    begin_time: int
    end_time: int = 0
    status: int = TaskStatus.OTHER
    total_layer: int = 0
    already_print_layer: int = 0
    error_status_reason: int = 0
    md5: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.end_time != 0


class HistoryStore:
    """Thread-safe, bounded, JSON-persisted task history."""

    def __init__(self, path: Path, limit: int = 50) -> None:
        self._path = path
        self._limit = max(1, limit)
        self._lock = threading.Lock()
        # Newest first, matching the ordered list command 320 expects.
        self._tasks: List[TaskRecord] = []
        self._load()

    # -- persistence ----------------------------------------------------

    def _load(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning("SDCP: discarding unreadable history at %s", self._path)
            return
        if not isinstance(data, list):
            return
        loaded: List[TaskRecord] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                loaded.append(TaskRecord(**entry))
            except TypeError:
                # A record written by a different version; skip rather than
                # throw the whole history away.
                continue
        self._tasks = loaded[: self._limit]

    def _save_locked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(
                json.dumps([asdict(t) for t in self._tasks], indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.warning("SDCP: could not persist history: %s", exc)

    # -- lifecycle ------------------------------------------------------

    def start_task(self, filename: str, total_layer: int = 0) -> Optional[str]:
        """Open a task for *filename*, or return the id of the open one."""
        if not filename:
            return None
        with self._lock:
            open_task = self._open_task_locked()
            if open_task is not None:
                if open_task.filename == filename:
                    if total_layer and not open_task.total_layer:
                        open_task.total_layer = total_layer
                        self._save_locked()
                    return open_task.task_id
                # A different file started without us seeing the old one end.
                self._close_locked(open_task, TaskStatus.OTHER)

            record = TaskRecord(
                task_id=uuid.uuid4().hex,
                filename=filename,
                begin_time=int(time.time()),
                total_layer=total_layer,
            )
            self._tasks.insert(0, record)
            if len(self._tasks) > self._limit:
                self._tasks = self._tasks[: self._limit]
            self._save_locked()
            logger.info("SDCP: opened history task for %s", filename)
            return record.task_id

    def update_progress(self, filename: str, layer: int, total_layer: int) -> None:
        with self._lock:
            task = self._open_task_locked()
            if task is None or task.filename != filename:
                return
            changed = False
            if layer > task.already_print_layer:
                task.already_print_layer = layer
                changed = True
            if total_layer and total_layer != task.total_layer:
                task.total_layer = total_layer
                changed = True
            if changed:
                self._save_locked()

    def finish_task(self, status: int) -> None:
        """Close the open task, if any, with *status*."""
        with self._lock:
            task = self._open_task_locked()
            if task is None:
                return
            self._close_locked(task, status)
            self._save_locked()
            logger.info(
                "SDCP: closed history task for %s (status %s)", task.filename, status
            )

    def _close_locked(self, task: TaskRecord, status: int) -> None:
        task.end_time = int(time.time())
        # A print that reached its last layer completed; anything else that
        # stopped early is recorded as stopped rather than completed.
        if status == TaskStatus.COMPLETED or (
            task.total_layer and task.already_print_layer >= task.total_layer
        ):
            task.status = TaskStatus.COMPLETED
        else:
            task.status = status

    def _open_task_locked(self) -> Optional[TaskRecord]:
        for task in self._tasks:
            if not task.finished:
                return task
        return None

    # -- queries --------------------------------------------------------

    def open_task_id(self) -> Optional[str]:
        with self._lock:
            task = self._open_task_locked()
            return task.task_id if task else None

    def task_ids(self) -> List[str]:
        with self._lock:
            return [t.task_id for t in self._tasks]

    def filename_for(self, task_id: str) -> Optional[str]:
        with self._lock:
            for task in self._tasks:
                if task.task_id == task_id:
                    return task.filename
            return None

    def details(self, task_ids: List[str], thumbnail_url: Any) -> List[Dict[str, Any]]:
        """Render the requested tasks as ``HistoryDetailList`` entries.

        *thumbnail_url* takes ``(task_id, filename)`` and returns an address,
        or "" when no preview can be produced. It is deliberately called
        outside the lock: it may touch the filesystem, and a callback that
        re-entered this store would deadlock on the non-reentrant lock.
        """
        with self._lock:
            wanted = list(task_ids) if task_ids else [t.task_id for t in self._tasks]
            by_id = {t.task_id: t for t in self._tasks}
            selected = [by_id[t] for t in wanted if t in by_id]

        entries: List[Dict[str, Any]] = []
        for task in selected:
            entries.append(
                {
                    "Thumbnail": thumbnail_url(task.task_id, task.filename),
                    "TaskName": task.filename,
                    "BeginTime": task.begin_time,
                    "EndTime": task.end_time,
                    "TaskStatus": task.status,
                    "SliceInformation": {},
                    "AlreadyPrintLayer": task.already_print_layer,
                    "TaskId": task.task_id,
                    "MD5": task.md5,
                    "CurrentLayerTalVolume": 0.0,
                    "TimeLapseVideoStatus": TimeLapseStatus.NOT_SHOT,
                    "TimeLapseVideoUrl": "",
                    "ErrorStatusReason": task.error_status_reason,
                }
            )
        return entries
