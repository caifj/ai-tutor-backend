"""Collect student outputs only; reference answers and grading stay in the case."""

MARKER = "__AI_TUTOR_CASE1_RESULT__"

HARNESS_SOURCE = r"""
import contextlib
import importlib.util
import io
import json
import sys

requests = json.loads(sys.stdin.read())
results = []
class Discard(io.TextIOBase):
    def write(self, text):
        return len(text)

def call(module, request):
    processes = request["processes"]
    algorithm = request["algorithm"]
    quantum = request["quantum"]
    if callable(getattr(module, "schedule", None)):
        result = module.schedule(processes, algorithm=algorithm, quantum=quantum)
    else:
        names = {"fcfs": "FCFSScheduler", "sjf": "SJFScheduler",
                 "rr": "RRScheduler", "priority": "PriorityScheduler"}
        cls = getattr(module, names[algorithm], None)
        pcb = getattr(module, "Process", None)
        if cls is None or pcb is None:
            raise ValueError("请实现 schedule(processes, algorithm, quantum=2)，"
                             "或提交 Process 与四个调度器类的单文件版本")
        scheduler = cls(quantum=quantum) if algorithm == "rr" else cls()
        result = scheduler.schedule([pcb(**p) for p in processes])
    if callable(getattr(result, "to_dict", None)):
        result = result.to_dict()
    # Freeze each result before the next call can mutate student-owned objects.
    return json.loads(json.dumps(result, allow_nan=False))

with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
    try:
        spec = importlib.util.spec_from_file_location("student", "student.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["student"] = module
        spec.loader.exec_module(module)
        for request in requests:
            try:
                results.append({"id": request["id"], "result": call(module, request)})
            except BaseException as exc:
                results.append({"id": request["id"], "error":
                                (type(exc).__name__ + ": " + str(exc))[:1000]})
        payload = {"results": results}
    except BaseException as exc:
        payload = {"load_error": (type(exc).__name__ + ": " + str(exc))[:1000]}

print("__AI_TUTOR_CASE1_RESULT__" + json.dumps(payload, ensure_ascii=False, allow_nan=False))
"""
