"""进程调度领域模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


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
    def from_dict(cls, data: Dict[str, Any]) -> "Process":
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
    segments: List[ExecutionSegment]
    process_metrics: List[ProcessMetrics]
    average_waiting_time: float
    average_turnaround_time: float
    average_response_time: float
    cpu_utilization: float
    total_time: int
    quantum: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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


"""FCFS、SJF、RR 和优先级调度算法实现。"""


from abc import ABC, abstractmethod
from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence


IDLE_PID = "IDLE"


class BaseScheduler(ABC):
    """调度器抽象基类，统一结果计算与数据校验。"""

    algorithm_name = "BASE"

    def schedule(self, processes: Sequence[Process]) -> ScheduleResult:
        clean_processes = self._validate_processes(processes)
        segments = self._simulate(clean_processes)
        return self._build_result(clean_processes, segments)

    @abstractmethod
    def _simulate(self, processes: Sequence[Process]) -> List[ExecutionSegment]:
        raise NotImplementedError

    def _result_quantum(self) -> Optional[int]:
        return None

    @staticmethod
    def _validate_processes(processes: Sequence[Process]) -> List[Process]:
        if not processes:
            raise ValueError("至少需要一个进程")
        result = list(processes)
        pids = [p.pid for p in result]
        if len(set(pids)) != len(pids):
            raise ValueError("pid 必须唯一")
        return result

    @staticmethod
    def _append_segment(
        segments: List[ExecutionSegment],
        pid: str,
        start: int,
        end: int,
        *,
        merge_adjacent: bool = True,
    ) -> None:
        if end <= start:
            return
        if merge_adjacent and segments and segments[-1].pid == pid and segments[-1].end == start:
            previous = segments[-1]
            segments[-1] = ExecutionSegment(pid=pid, start=previous.start, end=end)
        else:
            segments.append(ExecutionSegment(pid=pid, start=start, end=end))

    def _build_result(
        self,
        processes: Sequence[Process],
        segments: Sequence[ExecutionSegment],
    ) -> ScheduleResult:
        first_start: Dict[str, int] = {}
        completion: Dict[str, int] = {}
        busy_time = 0

        for segment in segments:
            if segment.pid == IDLE_PID:
                continue
            busy_time += segment.duration
            first_start.setdefault(segment.pid, segment.start)
            completion[segment.pid] = segment.end

        metrics: List[ProcessMetrics] = []
        for process in sorted(processes, key=lambda p: (p.arrival_time, p.pid)):
            if process.pid not in completion:
                raise RuntimeError(f"进程 {process.pid} 未完成调度")
            turnaround = completion[process.pid] - process.arrival_time
            waiting = turnaround - process.burst_time
            response = first_start[process.pid] - process.arrival_time
            metrics.append(
                ProcessMetrics(
                    pid=process.pid,
                    arrival_time=process.arrival_time,
                    burst_time=process.burst_time,
                    priority=process.priority,
                    first_start_time=first_start[process.pid],
                    completion_time=completion[process.pid],
                    waiting_time=waiting,
                    turnaround_time=turnaround,
                    response_time=response,
                )
            )

        count = len(metrics)
        total_time = segments[-1].end if segments else 0
        cpu_utilization = (busy_time / total_time * 100.0) if total_time else 0.0
        return ScheduleResult(
            algorithm=self.algorithm_name,
            quantum=self._result_quantum(),
            segments=list(segments),
            process_metrics=metrics,
            average_waiting_time=sum(m.waiting_time for m in metrics) / count,
            average_turnaround_time=sum(m.turnaround_time for m in metrics) / count,
            average_response_time=sum(m.response_time for m in metrics) / count,
            cpu_utilization=cpu_utilization,
            total_time=total_time,
            metadata={"priority_rule": "smaller_number_higher_priority"},
        )


class FCFSScheduler(BaseScheduler):
    """先来先服务（First-Come, First-Served）。"""

    algorithm_name = "FCFS"

    def _simulate(self, processes: Sequence[Process]) -> List[ExecutionSegment]:
        current_time = 0
        segments: List[ExecutionSegment] = []
        for process in sorted(processes, key=lambda p: (p.arrival_time, p.pid)):
            if current_time < process.arrival_time:
                self._append_segment(segments, IDLE_PID, current_time, process.arrival_time)
                current_time = process.arrival_time
            self._append_segment(
                segments, process.pid, current_time, current_time + process.burst_time
            )
            current_time += process.burst_time
        return segments


class SJFScheduler(BaseScheduler):
    """非抢占式短作业优先（Shortest Job First）。"""

    algorithm_name = "SJF_NON_PREEMPTIVE"

    def _simulate(self, processes: Sequence[Process]) -> List[ExecutionSegment]:
        pending = list(processes)
        current_time = 0
        segments: List[ExecutionSegment] = []

        while pending:
            ready = [p for p in pending if p.arrival_time <= current_time]
            if not ready:
                next_arrival = min(p.arrival_time for p in pending)
                self._append_segment(segments, IDLE_PID, current_time, next_arrival)
                current_time = next_arrival
                continue

            process = min(ready, key=lambda p: (p.burst_time, p.arrival_time, p.pid))
            pending.remove(process)
            self._append_segment(
                segments, process.pid, current_time, current_time + process.burst_time
            )
            current_time += process.burst_time

        return segments


class PriorityScheduler(BaseScheduler):
    """非抢占式优先级调度；priority 数字越小，优先级越高。"""

    algorithm_name = "PRIORITY_NON_PREEMPTIVE"

    def _simulate(self, processes: Sequence[Process]) -> List[ExecutionSegment]:
        pending = list(processes)
        current_time = 0
        segments: List[ExecutionSegment] = []

        while pending:
            ready = [p for p in pending if p.arrival_time <= current_time]
            if not ready:
                next_arrival = min(p.arrival_time for p in pending)
                self._append_segment(segments, IDLE_PID, current_time, next_arrival)
                current_time = next_arrival
                continue

            process = min(ready, key=lambda p: (p.priority, p.arrival_time, p.pid))
            pending.remove(process)
            self._append_segment(
                segments, process.pid, current_time, current_time + process.burst_time
            )
            current_time += process.burst_time

        return segments


class RRScheduler(BaseScheduler):
    """时间片轮转（Round Robin）。"""

    algorithm_name = "ROUND_ROBIN"

    def __init__(self, quantum: int = 2) -> None:
        if quantum <= 0:
            raise ValueError("时间片 quantum 必须大于 0")
        self.quantum = quantum

    def _result_quantum(self) -> Optional[int]:
        return self.quantum

    def _simulate(self, processes: Sequence[Process]) -> List[ExecutionSegment]:
        ordered = sorted(processes, key=lambda p: (p.arrival_time, p.pid))
        remaining = {p.pid: p.burst_time for p in ordered}
        queue: deque[Process] = deque()
        segments: List[ExecutionSegment] = []
        current_time = 0
        next_index = 0

        while queue or next_index < len(ordered):
            if not queue:
                next_arrival = ordered[next_index].arrival_time
                if current_time < next_arrival:
                    self._append_segment(segments, IDLE_PID, current_time, next_arrival)
                    current_time = next_arrival
                while next_index < len(ordered) and ordered[next_index].arrival_time <= current_time:
                    queue.append(ordered[next_index])
                    next_index += 1

            process = queue.popleft()
            run_time = min(self.quantum, remaining[process.pid])
            self._append_segment(
                segments,
                process.pid,
                current_time,
                current_time + run_time,
                merge_adjacent=False,
            )
            current_time += run_time
            remaining[process.pid] -= run_time

            while next_index < len(ordered) and ordered[next_index].arrival_time <= current_time:
                queue.append(ordered[next_index])
                next_index += 1

            if remaining[process.pid] > 0:
                queue.append(process)

        return segments
