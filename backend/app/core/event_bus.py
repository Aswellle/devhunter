"""
app/core/event_bus.py
线程安全的执行事件总线：Worker 线程发布，SSE 端点订阅。
"""
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExecutionEvent:
    task_id: str
    event_type: str   # start|fetch|parse|dedup|save|success|failure|warning|step
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


class EventBus:
    """
    每个 task_id 可被多个 SSE 客户端订阅。
    Worker 线程调用 publish()，SSE 端点调用 subscribe()/unsubscribe()。
    """

    def __init__(self, queue_size: int = 200) -> None:
        self._lock = threading.Lock()
        # task_id → [Queue, ...]
        self._queues: dict[str, list[queue.Queue]] = {}
        self._queue_size = queue_size

    def subscribe(self, task_id: str) -> "queue.Queue[ExecutionEvent]":
        """订阅指定任务的事件，返回专属 Queue。"""
        q: queue.Queue = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._queues.setdefault(task_id, []).append(q)
        return q

    def unsubscribe(self, task_id: str, q: "queue.Queue[ExecutionEvent]") -> None:
        """客户端断连时取消订阅，清理 Queue。"""
        with self._lock:
            listeners = self._queues.get(task_id, [])
            try:
                listeners.remove(q)
            except ValueError:
                pass
            if not listeners:
                self._queues.pop(task_id, None)

    def publish(self, event: ExecutionEvent) -> None:
        """向所有订阅者广播事件（非阻塞，队列满则丢弃）。"""
        with self._lock:
            queues = list(self._queues.get(event.task_id, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # 客户端消费太慢，丢弃事件

    def has_listeners(self, task_id: str) -> bool:
        with self._lock:
            return bool(self._queues.get(task_id))


# 全局单例
event_bus = EventBus()


def publish_event(task_id: str, event_type: str, message: str, data: dict | None = None) -> None:
    """便捷函数：安全发布事件，永不抛异常。"""
    try:
        event_bus.publish(ExecutionEvent(
            task_id=task_id,
            event_type=event_type,
            message=message,
            data=data or {},
        ))
    except Exception:
        pass
