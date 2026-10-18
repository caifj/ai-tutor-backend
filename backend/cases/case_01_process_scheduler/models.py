"""进程调度领域模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Process:
    """进程控制块（PCB）的精简模型。

    priority 数值越小，优先级越高。
    """

    pid: str
    arrival_time: int
    burst_time: int
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.pid or not self.pid.strip():
            raise ValueError("pid 不能为空")
        if self.arrival_time < 0:
            raise ValueError("arrival_time 不能小于 0")
        if self.burst_time <= 0:
            raise ValueError("burst_time 必须大于 0")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Process:
        """从 JSON 字典构造进程对象。"""
        return cls(
            pid=str(data["pid"]),
            arrival_time=int(data["arrival_time"]),
            burst_time=int(data["burst_time"]),
            priority=int(data.get("priority", 0)),
        )


@dataclass(frozen=True)
class ExecutionSegment:
    """甘特图中的一个连续执行片段。"""

    pid: str
    start: int
    end: int

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class ProcessMetrics:
    """单个进程的调度性能指标。"""

    pid: str
    arrival_time: int
    burst_time: int
    priority: int
    first_start_time: int
    completion_time: int
    waiting_time: int
    turnaround_time: int
    response_time: int


@dataclass
class ScheduleResult:
    """一次调度运行的完整结果。"""

    algorithm: str
    segments: list[ExecutionSegment]
    process_metrics: list[ProcessMetrics]
    average_waiting_time: float
    average_turnaround_time: float
    average_response_time: float
    cpu_utilization: float
    total_time: int
    quantum: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化的标准化 JSON 数据。"""
        return {
            "algorithm": self.algorithm,
            "quantum": self.quantum,
            "segments": [asdict(item) | {"duration": item.duration} for item in self.segments],
            "process_metrics": [asdict(item) for item in self.process_metrics],
            "summary": {
                "average_waiting_time": round(self.average_waiting_time, 4),
                "average_turnaround_time": round(self.average_turnaround_time, 4),
                "average_response_time": round(self.average_response_time, 4),
                "cpu_utilization_percent": round(self.cpu_utilization, 4),
                "total_time": self.total_time,
            },
            "metadata": self.metadata,
        }
