"""案例2：虚拟内存分页模拟器的参考实现。

本模块是基座自带的**标准答案数据源**：它不运行学生代码，而是用操作系统教材中约定的
页面访问序列，分别驱动 FIFO、LRU、OPT（最佳置换）三种页面置换算法，输出

- 内存页框数与缺页率的对应关系；
- 缺页率随内存页框数变化的曲线数据；
- 页框占用时间线（某个页框在一段时间内被哪个逻辑页占用）。

评测结果中的这两类数据与学生代码的静态检查结果一并返回给学生，用于对照自身实现的
缺页率曲线是否正确。

算法说明：

- FIFO：置换装入时间最早的页框（先进先出）。
- LRU：置换最近最久未被访问的页框。
- OPT：置换未来最长时间不再被访问的页框（Belady 最优算法），在已知完整引用串时可精确求解。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

ALGORITHM_FIFO = "FIFO"
ALGORITHM_LRU = "LRU"
ALGORITHM_OPT = "OPT"

#: 三种页面置换算法的展示顺序，也是曲线图例顺序。
ALGORITHMS: tuple[str, ...] = (ALGORITHM_FIFO, ALGORITHM_LRU, ALGORITHM_OPT)

#: 参考工作集中出现的逻辑页总数。
REFERENCE_PAGE_SPAN = 9
#: 缺页率曲线覆盖的物理内存页框数区间（1 ~ 页总数）。
FRAME_COUNT_RANGE: tuple[int, ...] = tuple(range(1, REFERENCE_PAGE_SPAN + 1))
#: 页框占用时间线只展示 LRU 算法在较小内存下的表现，避免数据量过大。
TIMELINE_ALGORITHM = ALGORITHM_LRU
TIMELINE_FRAME_COUNT = 4

#: 阶段一（工作集爬坡）：元组含义为 (起始逻辑页, 工作集大小, 重复次数)。
#: 工作集从 2 页逐步扩大到 8 页并反复访问，用于形成时间局部性，
#: 使"内存页框数增加 → 缺页率单调下降"的曲线具备完整的下降区间。
RAMP_WORKLOAD: tuple[tuple[int, int, int], ...] = (
    (0, 2, 3),
    (2, 3, 2),
    (5, 4, 2),
    (1, 5, 2),
    (3, 6, 2),
    (0, 7, 2),
    (2, 8, 2),
)

#: 阶段二（Belady 异常引用串）：教材中经典的 1 2 3 4 1 2 5 1 2 3 4 5，这里改为 0 起始页号。
#: 在 3 个页框时 FIFO 的缺页次数反而少于 LRU，用于验证学生实现是否真的区分了两种策略。
BELADY_CORE: tuple[int, ...] = (0, 1, 2, 3, 0, 1, 4, 0, 1, 2, 3, 4)

#: Belady 引用串在完整序列中重复的次数。
BELADY_REPEATS = 2


def build_reference_sequence(
    ramp_workload: tuple[tuple[int, int, int], ...] = RAMP_WORKLOAD,
    belady_core: tuple[int, ...] = BELADY_CORE,
    belady_repeats: int = BELADY_REPEATS,
    page_span: int = REFERENCE_PAGE_SPAN,
) -> tuple[int, ...]:
    """构造确定性的页面访问序列，共 96 次访问、覆盖 9 个逻辑页。

    序列由两段组成：

    1. 工作集爬坡段：工作集大小从 2 页递增到 8 页，每档重复若干次，使缺页率随内存页框数
       增大而稳定下降；
    2. Belady 异常段：追加若干次经典异常引用串，使 FIFO 与 LRU 的曲线在中段出现交叉，
       体现"先进先出并不总是优于最近最久未使用"。

    整个构造过程完全确定，任何一次评测都会得到逐位一致的标准答案。
    """

    sequence: list[int] = []
    for start, size, repeat in ramp_workload:
        window = tuple((start + offset) % page_span for offset in range(size))
        for _ in range(repeat):
            sequence.extend(window)
    for _ in range(belady_repeats):
        sequence.extend(belady_core)
    return tuple(sequence)


#: 所有评测共用的页面访问序列。
REFERENCE_SEQUENCE: tuple[int, ...] = build_reference_sequence()


@dataclass(frozen=True)
class FrameSegment:
    """页框占用时间线中的一条记录。

    区间为左闭右开：页框 ``frame_index`` 在第 ``start`` 次访问之后开始持有 ``page_number``，
    一直持续到第 ``end`` 次访问之前。``page_number`` 为 ``None`` 表示该页框尚未分配。
    """

    frame_index: int
    start: int
    end: int
    page_number: int | None


@dataclass(frozen=True)
class SimulationResult:
    """单次模拟的完整结果。"""

    algorithm: str
    frame_count: int
    reference_length: int
    page_faults: int
    frame_hits: int
    frames: tuple[int | None, ...]
    segments: tuple[FrameSegment, ...]

    @property
    def page_fault_rate(self) -> float:
        """缺页率，单位为百分比。"""

        if not self.reference_length:
            return 0.0
        return self.page_faults / self.reference_length * 100

    def to_sample(self) -> FaultRateSample:
        return FaultRateSample(
            algorithm=self.algorithm,
            frame_count=self.frame_count,
            reference_length=self.reference_length,
            page_faults=self.page_faults,
            frame_hits=self.frame_hits,
            page_fault_rate=round(self.page_fault_rate, 2),
        )


@dataclass(frozen=True)
class FaultRateSample:
    """缺页率曲线上的一个采样点。"""

    algorithm: str
    frame_count: int
    reference_length: int
    page_faults: int
    frame_hits: int
    page_fault_rate: float


def _next_use(sequence: tuple[int, ...], page: int, step: int) -> int | None:
    """返回逻辑页 ``page`` 在第 ``step`` 次访问之后的首次出现位置。"""

    for offset in range(step + 1, len(sequence)):
        if sequence[offset] == page:
            return offset
    return None


def _select_victim(
    frames: list[int | None],
    sequence: tuple[int, ...],
    step: int,
    used_at: list[int],
    fifo_order: deque[int],
    algorithm: str,
) -> int:
    """选择本次缺页要占用的页框下标。"""

    if None in frames:
        return frames.index(None)
    if algorithm == ALGORITHM_FIFO:
        return fifo_order.popleft()
    if algorithm == ALGORITHM_LRU:
        return min(range(len(frames)), key=lambda index: used_at[index])
    if algorithm == ALGORITHM_OPT:
        return _select_optimal_victim(frames, sequence, step)
    raise ValueError(f"未知的页面置换算法: {algorithm}")


def _select_optimal_victim(
    frames: list[int | None],
    sequence: tuple[int, ...],
    step: int,
) -> int:
    """OPT：置换未来最长时间不再被访问的页框。

    若某个页框内的逻辑页在后续引用串中永不出现，则认为它的下一次访问时间为无穷大，
    优先被换出；同样为无穷大时取下标最小者，保证结果可复现。
    """

    victim = 0
    best_key = (-1.0, float("-inf"))
    for index, page in enumerate(frames):
        next_use = _next_use(sequence, int(page), step)
        reach = float("inf") if next_use is None else float(next_use)
        key = (reach, float(-index))
        if key > best_key:
            best_key = key
            victim = index
    return victim


def _build_segments(
    snapshots: list[tuple[int | None, ...]],
    frame_count: int,
) -> tuple[FrameSegment, ...]:
    """把每次访问后的页框快照压缩为页框占用时间线。"""

    segments: list[FrameSegment] = []
    total_steps = len(snapshots)
    for frame_index in range(frame_count):
        start = 0
        current = snapshots[0][frame_index]
        for step in range(1, total_steps):
            value = snapshots[step][frame_index]
            if value != current:
                segments.append(
                    FrameSegment(
                        frame_index=frame_index,
                        start=start,
                        end=step,
                        page_number=current,
                    )
                )
                start = step
                current = value
        segments.append(
            FrameSegment(
                frame_index=frame_index,
                start=start,
                end=total_steps,
                page_number=current,
            )
        )
    return tuple(segments)


def simulate(
    sequence: tuple[int, ...] = REFERENCE_SEQUENCE,
    frame_count: int = REFERENCE_PAGE_SPAN,
    algorithm: str = ALGORITHM_FIFO,
) -> SimulationResult:
    """按指定置换算法模拟分页过程。

    ``frame_count`` 表示物理内存中可用的页框数量；算法在 ``algorithm`` 指定的三者之一。
    """

    if frame_count <= 0:
        raise ValueError("物理内存页框数必须为正整数")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"未知的页面置换算法: {algorithm}")
    if not sequence:
        raise ValueError("页面访问序列不能为空")

    frames: list[int | None] = [None] * frame_count
    used_at: list[int] = [-1] * frame_count
    fifo_order: deque[int] = deque()
    snapshots: list[tuple[int | None, ...]] = []
    page_faults = 0

    for step, page in enumerate(sequence):
        resident_index = next(
            (index for index, value in enumerate(frames) if value == page), None
        )
        if resident_index is None:
            page_faults += 1
            victim = _select_victim(frames, sequence, step, used_at, fifo_order, algorithm)
            resident_index = victim
            frames[victim] = page
            fifo_order.append(victim)
        used_at[resident_index] = step
        snapshots.append(tuple(frames))

    return SimulationResult(
        algorithm=algorithm,
        frame_count=frame_count,
        reference_length=len(sequence),
        page_faults=page_faults,
        frame_hits=len(sequence) - page_faults,
        frames=tuple(frames),
        segments=_build_segments(snapshots, frame_count),
    )


def fault_rate_curve(
    sequence: tuple[int, ...] = REFERENCE_SEQUENCE,
    frame_counts: tuple[int, ...] = FRAME_COUNT_RANGE,
    algorithms: tuple[str, ...] = ALGORITHMS,
) -> tuple[FaultRateSample, ...]:
    """输出"内存页框数 → 缺页率"的全部采样点，按算法分组后再按页框数升序排列。"""

    samples: list[FaultRateSample] = []
    for algorithm in algorithms:
        for frame_count in frame_counts:
            samples.append(simulate(sequence, frame_count, algorithm).to_sample())
    return tuple(samples)


def occupancy_timeline(
    sequence: tuple[int, ...] = REFERENCE_SEQUENCE,
    frame_count: int = TIMELINE_FRAME_COUNT,
    algorithm: str = TIMELINE_ALGORITHM,
) -> tuple[FrameSegment, ...]:
    """页框占用时间线，用于直观展示内存页框中页面被换入换出的过程。"""

    return simulate(sequence, frame_count, algorithm).segments


def average_fault_rates(
    sequence: tuple[int, ...] = REFERENCE_SEQUENCE,
    frame_counts: tuple[int, ...] = FRAME_COUNT_RANGE,
    algorithms: tuple[str, ...] = ALGORITHMS,
) -> dict[str, float]:
    """各置换算法在全部内存页框档位上的平均缺页率，单位为百分比。

    内存恰好容纳整个工作集时三种算法的缺页率完全相同，只有跨档位求平均才能真实反映
    "整体最优算法"。
    """

    grouped: dict[str, list[float]] = {algorithm: [] for algorithm in algorithms}
    for sample in fault_rate_curve(sequence, frame_counts, algorithms):
        grouped[sample.algorithm].append(sample.page_fault_rate)
    return {
        algorithm: round(sum(values) / len(values), 2)
        for algorithm, values in grouped.items()
        if values
    }


def best_algorithm(
    sequence: tuple[int, ...] = REFERENCE_SEQUENCE,
    frame_counts: tuple[int, ...] = FRAME_COUNT_RANGE,
    algorithms: tuple[str, ...] = ALGORITHMS,
) -> tuple[str, float]:
    """返回全区间平均缺页率最低的置换算法及其平均缺页率。"""

    averages = average_fault_rates(sequence, frame_counts, algorithms)
    name = min(averages, key=lambda key: averages[key])
    return name, averages[name]


def find_belady_anomaly(
    samples: tuple[FaultRateSample, ...],
) -> tuple[int, float, float] | None:
    """查找 FIFO 缺页率反而低于 LRU 的页框数，即 Belady 异常。

    返回 ``(页框数, FIFO 缺页率, LRU 缺页率)``；不存在异常时返回 ``None``。
    """

    rates = {
        (sample.algorithm, sample.frame_count): sample.page_fault_rate for sample in samples
    }
    for frame_count in sorted({sample.frame_count for sample in samples}):
        fifo_rate = rates.get((ALGORITHM_FIFO, frame_count))
        lru_rate = rates.get((ALGORITHM_LRU, frame_count))
        if fifo_rate is None or lru_rate is None or fifo_rate >= lru_rate:
            continue
        return frame_count, fifo_rate, lru_rate
    return None