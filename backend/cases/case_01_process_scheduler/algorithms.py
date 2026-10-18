"""FCFS、SJF、RR 和优先级调度算法实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Sequence

from .models import ExecutionSegment, Process, ProcessMetrics, ScheduleResult

IDLE_PID = "IDLE"


class BaseScheduler(ABC):
    """调度器抽象基类，统一结果计算与数据校验。"""

    algorithm_name = "BASE"

    def schedule(self, processes: Sequence[Process]) -> ScheduleResult:
        clean_processes = self._validate_processes(processes)
        segments = self._simulate(clean_processes)
        return self._build_result(clean_processes, segments)

    @abstractmethod
    def _simulate(self, processes: Sequence[Process]) -> list[ExecutionSegment]:
        raise NotImplementedError

    def _result_quantum(self) -> int | None:
        return None

    @staticmethod
    def _validate_processes(processes: Sequence[Process]) -> list[Process]:
        if not processes:
            raise ValueError("至少需要一个进程")
        result = list(processes)
        pids = [p.pid for p in result]
        if len(set(pids)) != len(pids):
            raise ValueError("pid 必须唯一")
        return result

    @staticmethod
    def _append_segment(
        segments: list[ExecutionSegment],
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
        first_start: dict[str, int] = {}
        completion: dict[str, int] = {}
        busy_time = 0

        for segment in segments:
            if segment.pid == IDLE_PID:
                continue
            busy_time += segment.duration
            first_start.setdefault(segment.pid, segment.start)
            completion[segment.pid] = segment.end

        metrics: list[ProcessMetrics] = []
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

    def _simulate(self, processes: Sequence[Process]) -> list[ExecutionSegment]:
        current_time = 0
        segments: list[ExecutionSegment] = []
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

    def _simulate(self, processes: Sequence[Process]) -> list[ExecutionSegment]:
        pending = list(processes)
        current_time = 0
        segments: list[ExecutionSegment] = []

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

    def _simulate(self, processes: Sequence[Process]) -> list[ExecutionSegment]:
        pending = list(processes)
        current_time = 0
        segments: list[ExecutionSegment] = []

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

    def _result_quantum(self) -> int | None:
        return self.quantum

    def _simulate(self, processes: Sequence[Process]) -> list[ExecutionSegment]:
        ordered = sorted(processes, key=lambda p: (p.arrival_time, p.pid))
        remaining = {p.pid: p.burst_time for p in ordered}
        queue: deque[Process] = deque()
        segments: list[ExecutionSegment] = []
        current_time = 0
        next_index = 0

        while queue or next_index < len(ordered):
            if not queue:
                next_arrival = ordered[next_index].arrival_time
                if current_time < next_arrival:
                    self._append_segment(segments, IDLE_PID, current_time, next_arrival)
                    current_time = next_arrival
                while (
                    next_index < len(ordered) and ordered[next_index].arrival_time <= current_time
                ):
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
