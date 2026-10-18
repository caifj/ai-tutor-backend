# -*- coding: utf-8 -*-
"""案例 8 运行时测试夹具（在沙箱中与 student.py 一起执行）。

学生需要实现（契约见 CaseDescriptor.description）::

    tokenize(source: str) -> list[dict]         # 每项至少 {"kind","lexeme","line","column"}
    parse(source: str)    -> dict               # {"ast": ..., "errors": [{"line","column","message"}]}

也接受把两者合并为一个 ``analyze(source) -> {"tokens","ast","errors"}``。

夹具只调用学生代码、核对行为，不做业务判断；结果通过标记行输出给案例适配器解析。
"""

MARKER = "__AI_TUTOR_CASE8_RESULT__"

# 正确程序：函数定义 + 变量声明 + 函数调用
GOOD_PROGRAM = """fn int add(int a, int b) {
    return a + b;
}

fn int main() {
    let x = 1;
    let y = 2;
    return add(x, y);
}
"""

# 语法错误 1：if 条件缺少右括号（第 3 行）
MISSING_PAREN_PROGRAM = """fn int main() {
    let a = 1;
    if (a > 0 {
        return 1;
    }
    return 0;
}
"""

# 语法错误 2：变量声明缺少分号（第 2 行）
MISSING_SEMI_PROGRAM = """fn int main() {
    let a = 1
    return a;
}
"""

HARNESS_SOURCE = r'''
"""案例 8 运行时夹具：调用学生的词法/语法分析实现并核对行为。"""

import json

MARKER = "__AI_TUTOR_CASE8_RESULT__"

GOOD_PROGRAM = """fn int add(int a, int b) {
    return a + b;
}

fn int main() {
    let x = 1;
    let y = 2;
    return add(x, y);
}
"""

MISSING_PAREN_PROGRAM = """fn int main() {
    let a = 1;
    if (a > 0 {
        return 1;
    }
    return 0;
}
"""

MISSING_SEMI_PROGRAM = """fn int main() {
    let a = 1
    return a;
}
"""


def add(checks, check_id, title, passed, evidence, weight=0):
    checks.append({
        "check_id": check_id,
        "title": title,
        "passed": bool(passed),
        "evidence": str(evidence)[:400],
        "weight": weight,
    })


def call_tokens(module, source):
    """优先用 analyze()，否则用 tokenize()。"""
    if hasattr(module, "analyze"):
        result = module.analyze(source)
        if isinstance(result, dict):
            return result.get("tokens")
    return module.tokenize(source)


def call_parse(module, source):
    if hasattr(module, "analyze"):
        result = module.analyze(source)
        if isinstance(result, dict):
            return result
    return module.parse(source)


def count_nodes(node, depth=0):
    """粗略统计 AST 中的节点数量（dict/list 都算一层）。"""
    if depth > 40:
        return 0
    total = 1
    if isinstance(node, dict):
        for value in node.values():
            total += count_nodes(value, depth + 1)
    elif isinstance(node, (list, tuple)):
        for item in node:
            total += count_nodes(item, depth + 1)
    return total


def main():
    checks = []

    # ---------- 1. 模块可导入且提供约定函数 ----------
    try:
        import student  # noqa: F401
        imported = True
        evidence = "student 模块导入成功"
    except Exception as exc:  # noqa: BLE001
        imported = False
        evidence = f"导入失败：{type(exc).__name__}: {exc}"

    add(checks, "IMPORT_MODULE", "提交的 Python 文件可被导入", imported, evidence, 5)
    if not imported:
        print(MARKER + json.dumps({"checks": checks, "observations": {}}))
        return

    has_tokenize = callable(getattr(student, "tokenize", None))
    has_parse = callable(getattr(student, "parse", None))
    has_analyze = callable(getattr(student, "analyze", None))
    add(checks, "API_TOKENIZE", "实现 tokenize(source) 词法分析接口",
        has_tokenize or has_analyze,
        "已提供 tokenize" if has_tokenize else ("已提供 analyze" if has_analyze else "缺少 tokenize/analyze"), 10)
    add(checks, "API_PARSE", "实现 parse(source) 语法分析接口",
        has_parse or has_analyze,
        "已提供 parse" if has_parse else ("已提供 analyze" if has_analyze else "缺少 parse/analyze"), 10)

    tokens = None
    ast = None
    errors = None

    # ---------- 2. 词法分析行为 ----------
    if has_tokenize or has_analyze:
        try:
            tokens = call_tokens(student, GOOD_PROGRAM)
            token_ok = isinstance(tokens, list) and len(tokens) > 10
            add(checks, "TOKENIZE_COUNT", "正确程序切分出足够多的 Token（>10）",
                token_ok, f"返回 {type(tokens).__name__}，长度 "
                f"{len(tokens) if isinstance(tokens, list) else 'N/A'}", 8)

            if isinstance(tokens, list) and tokens:
                dict_tokens = [t for t in tokens if isinstance(t, dict)]
                fields_ok = bool(dict_tokens) and all(
                    isinstance(t.get("kind"), str) and t.get("kind")
                    and isinstance(t.get("lexeme"), str) and t.get("lexeme") is not None
                    for t in dict_tokens
                )
                add(checks, "TOKENIZE_FIELDS", "每个 Token 含非空 kind 与 lexeme", fields_ok,
                    f"{len(dict_tokens)}/{len(tokens)} 个 Token 为 dict："
                    f"{dict_tokens[:3]}", 8)

                pos_ok = all(
                    isinstance(t.get("line"), int) and t.get("line", 0) >= 1
                    and isinstance(t.get("column"), int) and t.get("column", 0) >= 1
                    for t in dict_tokens
                ) and bool(dict_tokens)
                add(checks, "TOKENIZE_POSITION", "Token 带行列信息（line/column ≥ 1）", pos_ok,
                    "全部 Token 含 line/column" if pos_ok else "存在缺失或非法行列", 8)

                lines = [t.get("line") for t in dict_tokens if isinstance(t.get("line"), int)]
                order_ok = bool(lines) and lines == sorted(lines)
                add(checks, "TOKENIZE_ORDER", "Token 行号单调不减（按源码顺序）", order_ok,
                    f"首行 {lines[0] if lines else '?'}，末行 {lines[-1] if lines else '?'}", 4)
        except Exception as exc:  # noqa: BLE001
            add(checks, "TOKENIZE_RUNTIME", "tokenize 对正确程序可正常返回", False,
                f"抛出 {type(exc).__name__}: {exc}", 8)

    # ---------- 3. 语法分析行为 ----------
    if has_parse or has_analyze:
        try:
            result = call_parse(student, GOOD_PROGRAM)
            if isinstance(result, dict):
                ast = result.get("ast")
                errors = result.get("errors")
            else:
                ast, errors = result, []
            add(checks, "PARSE_RETURN_DICT", "parse 返回含 ast/errors 的字典",
                isinstance(result, dict),
                f"返回 {type(result).__name__}", 6)

            node_count = count_nodes(ast)
            add(checks, "PARSE_AST_NODES", "为正确程序构造出语法树（节点数 ≥ 5）",
                node_count >= 5, f"AST 节点数约 {node_count}", 10)

            clean = isinstance(errors, (list, tuple)) and len(errors) == 0
            add(checks, "PARSE_NO_FALSE_ERROR", "正确程序不报语法错误", clean,
                f"errors={errors!r}"[:300], 8)
        except Exception as exc:  # noqa: BLE001
            add(checks, "PARSE_RUNTIME", "parse 对正确程序可正常返回", False,
                f"抛出 {type(exc).__name__}: {exc}", 10)

    # ---------- 4. 语法错误定位 ----------
    errs = []
    errs2 = []

    def error_list(source):
        result = call_parse(student, source)
        if isinstance(result, dict):
            items = result.get("errors")
            return items if isinstance(items, (list, tuple)) else []
        return []

    try:
        errs = error_list(MISSING_PAREN_PROGRAM)
        detected = len(errs) >= 1
        add(checks, "ERROR_DETECT_PAREN", "检出 if 条件缺少右括号", detected,
            f"报出 {len(errs)} 条错误：{errs[:2]!r}"[:300], 8)

        located = False
        message_ok = False
        if errs and isinstance(errs[0], dict):
            first = errs[0]
            line = first.get("line")
            column = first.get("column")
            located = line == 3 and (not isinstance(column, int) or 12 <= column <= 18)
            message_ok = isinstance(first.get("message"), str) and bool(first.get("message"))
        add(checks, "ERROR_LOCATION_PAREN", "错误定位到第 3 行（允许列号容差）", located,
            f"首条错误={errs[0] if errs else None!r}"[:300], 8)
        add(checks, "ERROR_MESSAGE_TEXT", "错误信息包含可读的消息文本", message_ok,
            f"message={errs[0].get('message') if errs else None!r}"[:300], 4)
    except Exception as exc:  # noqa: BLE001
        add(checks, "ERROR_DETECT_PAREN", "检出并定位语法错误", False,
            f"抛出 {type(exc).__name__}: {exc}", 8)

    try:
        errs2 = error_list(MISSING_SEMI_PROGRAM)
        add(checks, "ERROR_DETECT_SEMI", "检出变量声明缺少分号", len(errs2) >= 1,
            f"报出 {len(errs2)} 条错误：{errs2[:2]!r}"[:300], 6)
    except Exception as exc:  # noqa: BLE001
        add(checks, "ERROR_DETECT_SEMI", "检出变量声明缺少分号", False,
            f"抛出 {type(exc).__name__}: {exc}", 6)

    # ---------- 5. 汇总 ----------
    observations = {
        "token_count": len(tokens) if isinstance(tokens, list) else 0,
        "ast_node_count": count_nodes(ast),
        "error_count_paren": len(errors) if isinstance(errors, list) else 0,
        # 下面三项供案例生成可视化数据集（web 页面展示 AST 与错误定位）
        "ast": ast,
        "errors_paren": list(errs) if isinstance(errs, (list, tuple)) else [],
        "errors_semi": list(errs2) if isinstance(errs2, (list, tuple)) else [],
        "tokens_preview": [
            {k: t.get(k) for k in ("kind", "lexeme", "line", "column")}
            for t in (tokens[:15] if isinstance(tokens, list) else []) if isinstance(t, dict)
        ],
    }
    print(MARKER + json.dumps({"checks": checks, "observations": observations}))


if __name__ == "__main__":
    main()
'''
