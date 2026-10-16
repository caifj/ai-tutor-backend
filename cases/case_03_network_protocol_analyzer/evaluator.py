from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceFacts:
    tree: ast.AST
    source: str
    calls: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    strings: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=list)
    classes: list[ast.ClassDef] = field(default_factory=list)
    containers: set[str] = field(default_factory=set)

    @property
    def searchable(self) -> str:
        values = self.calls | self.names | self.strings | self.imports
        return " ".join(sorted(values)).lower()


@dataclass
class EvaluationReport:
    syntax_valid: bool
    functional_checks: list[dict[str, Any]]
    quality_scores: list[dict[str, Any]]
    issues: list[dict[str, Any]]

    @property
    def tests_total(self) -> int:
        return len(self.functional_checks)

    @property
    def tests_passed(self) -> int:
        return sum(bool(item["passed"]) for item in self.functional_checks)

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total * 100 if self.tests_total else 0.0

    @property
    def functionality_score(self) -> float:
        return sum(float(item["earned"]) for item in self.functional_checks)

    def quality_score(self, dimension: str) -> float:
        return next(
            (float(row["score"]) for row in self.quality_scores if row["dimension"] == dimension),
            0.0,
        )

    @property
    def pep8_score(self) -> float:
        return self.quality_score("PEP8 规范")

    @property
    def modularity_score(self) -> float:
        return self.quality_score("模块化程度")

    @property
    def duplication_score(self) -> float:
        return self.quality_score("重复代码")

    @property
    def overall_score(self) -> float:
        return min(
            100.0,
            self.functionality_score
            + self.pep8_score
            + self.modularity_score
            + self.duplication_score,
        )


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


class FactVisitor(ast.NodeVisitor):
    def __init__(self, facts: SourceFacts) -> None:
        self.facts = facts

    def visit_Call(self, node: ast.Call) -> None:
        name = _qualified_name(node.func)
        if name:
            self.facts.calls.add(name.lower())
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.facts.names.add(node.id.lower())

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.facts.names.add(node.attr.lower())
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            normalized = " ".join(node.value.lower().split())
            if normalized:
                self.facts.strings.add(normalized[:300])

    def visit_Import(self, node: ast.Import) -> None:
        self.facts.imports.update(alias.name.lower() for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = (node.module or "").lower()
        self.facts.imports.add(module)
        self.facts.imports.update(f"{module}.{alias.name.lower()}" for alias in node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.facts.functions.append(node)
        self.facts.names.add(node.name.lower())
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.facts.functions.append(node)
        self.facts.names.add(node.name.lower())
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.facts.classes.append(node)
        self.facts.names.add(node.name.lower())
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self.facts.containers.add("dict")
        self.generic_visit(node)

    def visit_Set(self, node: ast.Set) -> None:
        self.facts.containers.add("set")
        self.generic_visit(node)


def _collect_facts(tree: ast.AST, source: str) -> SourceFacts:
    facts = SourceFacts(tree=tree, source=source)
    FactVisitor(facts).visit(tree)
    return facts


def _has_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def _function_context(facts: SourceFacts, protocol: str, actions: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for function in facts.functions:
        name = function.name.lower()
        segment = (ast.get_source_segment(facts.source, function) or "").lower()
        if protocol in segment and any(action in name or action in segment for action in actions):
            matches.append(function.name)
    return matches


def _evidence(names: list[str], success: str, failure: str) -> str:
    return f"{success}：{', '.join(names[:4])}" if names else failure


def _feature_checks(facts: SourceFacts) -> list[dict[str, Any]]:
    text = facts.searchable
    scapy = "scapy" in text
    raw_build = "struct.pack" in facts.calls or "bytearray" in facts.calls
    raw_parse = "struct.unpack" in facts.calls or "int.from_bytes" in facts.calls
    build_actions = ("build", "craft", "create", "construct")
    parse_actions = ("parse", "decode", "analy")
    build_arp = _function_context(facts, "arp", build_actions)
    build_icmp = _function_context(facts, "icmp", build_actions)
    build_tcp = _function_context(facts, "tcp", build_actions)
    parse_arp = _function_context(facts, "arp", parse_actions)
    parse_icmp = _function_context(facts, "icmp", parse_actions)
    parse_tcp = _function_context(facts, "tcp", parse_actions)

    capture_calls = sorted(
        call
        for call in facts.calls
        if _has_any(call, ("sniff", "recvfrom", "recv", "capture", "pcap"))
    )
    scan_functions = [
        function.name
        for function in facts.functions
        if _has_any(function.name.lower(), ("scan", "anomal", "detect", "suspicious"))
    ]
    has_threshold = "len" in facts.calls and _has_any(
        text, ("threshold", "scan", "unique_ports", "distinct_ports", "syn_count")
    )
    output_keys = tuple(
        key
        for key in (
            "packet_records",
            "capture_records",
            "anomaly_findings",
            "anomalies",
            "scan_results",
        )
        if key in text
    )
    serializers = sorted(
        call for call in facts.calls if _has_any(call, ("json.dump", "csv.writer", "dictwriter"))
    )

    definitions: list[tuple[str, str, float, bool, str, str]] = [
        (
            "BUILD_ARP",
            "构造 ARP 报文",
            8.0,
            bool(build_arp) and (scapy or raw_build),
            _evidence(build_arp, "检测到 ARP 构造函数", "未定位到完整的 ARP 构造逻辑"),
            "提供包含 ARP 字段赋值的构造函数，并使用 Scapy 或 struct.pack。",
        ),
        (
            "BUILD_ICMP",
            "构造 ICMP 报文",
            8.0,
            bool(build_icmp) and (scapy or raw_build),
            _evidence(build_icmp, "检测到 ICMP 构造函数", "未定位到完整的 ICMP 构造逻辑"),
            "实现 ICMP 报文构造；原始字节实现应包含校验和处理。",
        ),
        (
            "BUILD_TCP",
            "构造 TCP 报文",
            8.0,
            bool(build_tcp) and (scapy or raw_build),
            _evidence(build_tcp, "检测到 TCP 构造函数", "未定位到完整的 TCP 构造逻辑"),
            "实现 TCP 首部、标志位与校验和，或正确组合 Scapy TCP 层。",
        ),
        (
            "CAPTURE_PACKETS",
            "捕获网络报文",
            10.0,
            bool(capture_calls),
            f"捕获调用：{', '.join(capture_calls[:4])}" if capture_calls else "未发现抓包 API 调用",
            "使用 scapy.sniff、socket.recvfrom 或等价抓包库，并限制数量和超时。",
        ),
        (
            "PARSE_ARP",
            "解析 ARP 报文",
            7.0,
            bool(parse_arp) and (scapy or raw_parse),
            _evidence(parse_arp, "检测到 ARP 解析函数", "未定位到完整的 ARP 解析逻辑"),
            "为 ARP 字段提取提供独立 parse/decode/analyze 函数。",
        ),
        (
            "PARSE_ICMP",
            "解析 ICMP 报文",
            7.0,
            bool(parse_icmp) and (scapy or raw_parse),
            _evidence(parse_icmp, "检测到 ICMP 解析函数", "未定位到完整的 ICMP 解析逻辑"),
            "提取 ICMP 类型、代码、标识符等关键字段。",
        ),
        (
            "PARSE_TCP",
            "解析 TCP 报文",
            7.0,
            bool(parse_tcp) and (scapy or raw_parse),
            _evidence(parse_tcp, "检测到 TCP 解析函数", "未定位到完整的 TCP 解析逻辑"),
            "提取端口、序列号和 TCP flags，并覆盖异常标志组合。",
        ),
        (
            "DETECT_SCAN",
            "识别扫描等异常流量",
            10.0,
            bool(scan_functions) and has_threshold and bool(facts.containers & {"dict", "set"}),
            (
                f"检测函数：{', '.join(scan_functions[:4])}；存在计数/阈值结构"
                if scan_functions and has_threshold
                else "未发现基于去重端口/目标与阈值的扫描检测逻辑"
            ),
            "按源地址聚合不同目的端口或主机，结合 SYN 标志和阈值输出告警。",
        ),
        (
            "STRUCTURED_OUTPUT",
            "输出抓包记录与异常识别结果",
            5.0,
            len(output_keys) >= 2 or bool(serializers),
            (
                f"输出字段/序列化：{', '.join((*output_keys, *serializers)[:5])}"
                if output_keys or serializers
                else "未发现抓包记录与异常结果的结构化输出"
            ),
            "返回含 packet_records 与 anomaly_findings 的字典，或导出 JSON/CSV。",
        ),
    ]
    return [
        {
            "check_id": check_id,
            "title": title,
            "passed": passed,
            "weight": weight,
            "earned": weight if passed else 0.0,
            "evidence": evidence,
            "suggestion": "已识别到对应实现。" if passed else suggestion,
        }
        for check_id, title, weight, passed, evidence, suggestion in definitions
    ]


def _issue(
    severity: str,
    line: int | None,
    code: str,
    message: str,
    suggestion: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "line": line,
        "code": code,
        "message": message,
        "suggestion": suggestion,
    }


def _quality_row(dimension: str, score: float, summary: str, details: str) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "score": score,
        "max_score": 10.0,
        "summary": summary,
        "details": details,
    }


def _pep8_quality(source: str, tree: ast.AST) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    score = 10.0
    issues: list[dict[str, Any]] = []
    lines = source.splitlines()
    long_lines = [number for number, line in enumerate(lines, 1) if len(line) > 100]
    tabs = [
        number
        for number, line in enumerate(lines, 1)
        if "\t" in line[: len(line) - len(line.lstrip())]
    ]
    trailing = [number for number, line in enumerate(lines, 1) if line.rstrip() != line]
    wildcard = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
    ]
    checks = [
        (long_lines, 3.0, "E501", "行长度超过 100 个字符", "拆分长表达式或长字符串。"),
        (tabs, 1.5, "W191", "缩进中使用了制表符", "统一使用 4 个空格缩进。"),
        (trailing, 1.0, "W291", "行尾存在多余空白", "删除行尾空白。"),
        (wildcard, 1.5, "F403", "使用了通配符导入", "显式导入所需名称。"),
    ]
    for positions, deduction, code, message, suggestion in checks:
        if positions:
            score -= min(deduction, len(positions) * 0.5)
            issues.extend(_issue("style", line, code, message, suggestion) for line in positions[:8])

    bad_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not re.fullmatch(r"[a-z_][a-z0-9_]*", node.name)
    ]
    if bad_names:
        score -= min(2.0, len(bad_names) * 0.5)
        issues.extend(
            _issue(
                "style",
                node.lineno,
                "N802",
                f"函数名 {node.name!r} 不符合 snake_case",
                "使用小写字母和下划线命名函数。",
            )
            for node in bad_names[:5]
        )
    score = max(0.0, round(score, 1))
    summary = "规范良好" if score >= 8 else "存在可改进的格式问题"
    details = (
        f"长行 {len(long_lines)}，Tab 缩进 {len(tabs)}，行尾空白 {len(trailing)}，"
        f"通配符导入 {len(wildcard)}。"
    )
    return _quality_row("PEP8 规范", score, summary, details), issues


def _modularity_quality(facts: SourceFacts) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    count = len(facts.functions)
    score = 0.0 if count == 0 else 4.0 if count == 1 else 6.0 if count <= 3 else 8.0
    issues: list[dict[str, Any]] = []
    documented = sum(bool(ast.get_docstring(function)) for function in facts.functions)
    score += 1.0 if facts.classes else 0.0
    score += 1.0 if count and documented / count >= 0.5 else 0.0
    long_functions: list[tuple[str, int, int]] = []
    for function in facts.functions:
        end = getattr(function, "end_lineno", function.lineno) or function.lineno
        length = end - function.lineno + 1
        if length > 60:
            long_functions.append((function.name, function.lineno, length))
            score -= 1.5
            issues.append(
                _issue(
                    "quality",
                    function.lineno,
                    "C901",
                    f"函数 {function.name!r} 长达 {length} 行",
                    "拆分抓包、协议解析、异常检测和输出职责。",
                )
            )
    if count < 4:
        issues.append(
            _issue(
                "quality",
                None,
                "MOD001",
                "可识别的函数数量偏少，职责可能未充分拆分",
                "为构造、捕获、解析和异常检测分别提供函数或类。",
            )
        )
    score = max(0.0, min(10.0, round(score, 1)))
    summary = "职责拆分清晰" if score >= 8 else "模块化程度仍可提升"
    details = (
        f"函数 {count} 个，类 {len(facts.classes)} 个，有文档字符串的函数 {documented} 个，"
        f"超过 60 行的函数 {len(long_functions)} 个。"
    )
    return _quality_row("模块化程度", score, summary, details), issues


def _duplication_quality(source: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ignored_lines: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        ignored_lines = {
            token.start[0] for token in tokens if token.type in {tokenize.COMMENT, tokenize.STRING}
        }
    except (tokenize.TokenError, IndentationError):
        pass
    logical = [
        (number, " ".join(line.strip().split()))
        for number, line in enumerate(source.splitlines(), 1)
        if number not in ignored_lines and len(" ".join(line.strip().split())) >= 8
    ]
    windows: dict[tuple[str, ...], list[int]] = {}
    for index in range(max(0, len(logical) - 3)):
        block = logical[index : index + 4]
        if any(block[offset + 1][0] != block[offset][0] + 1 for offset in range(3)):
            continue
        windows.setdefault(tuple(item[1] for item in block), []).append(block[0][0])
    repeated = [lines for lines in windows.values() if len(lines) > 1]
    score = max(0.0, 10.0 - min(8.0, len(repeated) * 2.0))
    issues = [
        _issue(
            "quality",
            lines[0],
            "DUP001",
            f"发现 4 行重复代码块，起始行：{', '.join(map(str, lines[:5]))}",
            "提取公共函数，使用参数表达协议间差异。",
        )
        for lines in repeated[:5]
    ]
    summary = "未发现明显重复" if not repeated else "存在可合并的重复代码"
    details = f"基于连续 4 个有效代码行比较，发现 {len(repeated)} 组重复片段。"
    return _quality_row("重复代码", score, summary, details), issues


def _security_issues(facts: SourceFacts) -> list[dict[str, Any]]:
    risky = {
        "eval": "eval 会执行动态表达式",
        "exec": "exec 会执行动态代码",
        "os.system": "os.system 会启动外部命令",
        "subprocess.run": "subprocess.run 会启动外部进程",
        "subprocess.popen": "subprocess.Popen 会启动外部进程",
    }
    issues: list[dict[str, Any]] = []
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.Call) and _qualified_name(node.func).lower() in risky:
            name = _qualified_name(node.func).lower()
            issues.append(
                _issue(
                    "warning",
                    node.lineno,
                    "SEC001",
                    risky[name],
                    "避免在网络分析任务中执行不受信任的代码或系统命令。",
                )
            )
    return issues


CHECK_DEFINITIONS = (
    ("BUILD_ARP", "构造 ARP 报文", 8.0),
    ("BUILD_ICMP", "构造 ICMP 报文", 8.0),
    ("BUILD_TCP", "构造 TCP 报文", 8.0),
    ("CAPTURE_PACKETS", "捕获网络报文", 10.0),
    ("PARSE_ARP", "解析 ARP 报文", 7.0),
    ("PARSE_ICMP", "解析 ICMP 报文", 7.0),
    ("PARSE_TCP", "解析 TCP 报文", 7.0),
    ("DETECT_SCAN", "识别扫描等异常流量", 10.0),
    ("STRUCTURED_OUTPUT", "输出抓包记录与异常识别结果", 5.0),
)


def _syntax_failure(exc: SyntaxError) -> EvaluationReport:
    checks = [
        {
            "check_id": check_id,
            "title": title,
            "passed": False,
            "weight": weight,
            "earned": 0.0,
            "evidence": "Python 语法解析失败，无法继续静态分析。",
            "suggestion": "先修复语法错误，再重新提交。",
        }
        for check_id, title, weight in CHECK_DEFINITIONS
    ]
    issue = _issue(
        "error",
        exc.lineno,
        "E999",
        f"Python 语法错误：{exc.msg}",
        "根据行号修复语法后重新提交。",
    )
    quality = [
        _quality_row("PEP8 规范", 0.0, "无法评分", "语法无效。"),
        _quality_row("模块化程度", 0.0, "无法评分", "语法无效。"),
        _quality_row("重复代码", 0.0, "无法评分", "语法无效。"),
    ]
    return EvaluationReport(False, checks, quality, [issue])


def evaluate_python_source(source: str) -> EvaluationReport:
    """Evaluate a submission without importing or executing it."""

    try:
        tree = ast.parse(source, filename="submission.py")
    except SyntaxError as exc:
        return _syntax_failure(exc)
    except ValueError as exc:
        return _syntax_failure(SyntaxError(str(exc), ("submission.py", 1, 1, "")))

    facts = _collect_facts(tree, source)
    pep8, pep8_issues = _pep8_quality(source, tree)
    modularity, modularity_issues = _modularity_quality(facts)
    duplication, duplication_issues = _duplication_quality(source)
    return EvaluationReport(
        syntax_valid=True,
        functional_checks=_feature_checks(facts),
        quality_scores=[pep8, modularity, duplication],
        issues=pep8_issues
        + modularity_issues
        + duplication_issues
        + _security_issues(facts),
    )
