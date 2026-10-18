# -*- coding: utf-8 -*-
"""MiniC 词法 / 语法分析器（案例 8 示例提交 · 合格版本）。

对外契约：

* ``tokenize(source) -> list[dict]``
  每个 Token 为 ``{"kind", "lexeme", "line", "column"}``。
* ``parse(source) -> {"ast": ..., "errors": [{"line", "column", "message"}]}``
  语法正确时 ``errors`` 为空列表；出错时给出首个可定位的错误并尽量恢复。

作者：示例提交（用于验证案例评测流程，可作学生参考实现）。
"""
from __future__ import annotations

KEYWORDS = {
    "fn", "let", "if", "else", "while", "return", "print", "println",
    "int", "real", "bool", "char", "string", "void", "true", "false",
}

# 可作为类型名使用的关键字
TYPE_NAMES = {"int", "real", "bool", "char", "string", "void"}

OPERATORS = [
    "==", "!=", "<=", ">=", "&&", "||", "++", "--",
    "+", "-", "*", "/", "%", "=", "<", ">", "!",
]

PUNCTUATION = "(){}[];,.:"


class LexError(Exception):
    """词法错误。"""


class ParseError(Exception):
    """语法错误，携带源码位置。"""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


def _is_alpha(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_alnum(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def tokenize(source: str) -> list[dict]:
    """把源码切分为 Token 列表，忽略空白与 ``//`` 行注释。"""
    tokens: list[dict] = []
    index = 0
    line = 1
    column = 1
    length = len(source)

    while index < length:
        ch = source[index]

        if ch == "\n":
            index += 1
            line += 1
            column = 1
            continue
        if ch in " \t\r":
            index += 1
            column += 1
            continue
        if ch == "/" and source[index:index + 2] == "//":
            while index < length and source[index] != "\n":
                index += 1
                column += 1
            continue

        start_col = column
        if _is_alpha(ch):
            start = index
            while index < length and _is_alnum(source[index]):
                index += 1
            word = source[start:index]
            kind = "关键字" if word in KEYWORDS else "标识符"
            tokens.append({"kind": kind, "lexeme": word, "line": line, "column": start_col})
            column += len(word)
            continue

        if ch.isdigit():
            start = index
            while index < length and (source[index].isdigit() or source[index] == "."):
                index += 1
            text = source[start:index]
            kind = "实数" if "." in text else "整数"
            tokens.append({"kind": kind, "lexeme": text, "line": line, "column": start_col})
            column += len(text)
            continue

        if ch == '"':
            start = index
            index += 1
            while index < length and source[index] not in '"\n':
                index += 1
            if index >= length or source[index] != '"':
                raise LexError(f"第 {line} 行字符串未闭合")
            index += 1
            text = source[start:index]
            tokens.append({"kind": "字符串", "lexeme": text, "line": line, "column": start_col})
            column += len(text)
            continue

        matched = None
        for op in OPERATORS:
            if source.startswith(op, index):
                matched = op
                break
        if matched:
            tokens.append({"kind": "运算符", "lexeme": matched, "line": line, "column": start_col})
            index += len(matched)
            column += len(matched)
            continue

        if ch in PUNCTUATION:
            tokens.append({"kind": "分隔符", "lexeme": ch, "line": line, "column": start_col})
            index += 1
            column += 1
            continue

        raise LexError(f"第 {line} 行第 {column} 列出现非法字符 {ch!r}")

    tokens.append({"kind": "文件结束", "lexeme": "<EOF>", "line": line, "column": column})
    return tokens


class Parser:
    """递归下降语法分析器，产出字典形态的 AST。"""

    def __init__(self, tokens: list[dict]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.errors: list[dict] = []

    # ---------------- 基础工具 ----------------
    @property
    def current(self) -> dict:
        return self.tokens[min(self.pos, len(self.tokens) - 1)]

    def advance(self) -> dict:
        token = self.current
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return token

    def at(self, lexeme: str) -> bool:
        return self.current["lexeme"] == lexeme

    def error(self, message: str, token: dict | None = None) -> None:
        token = token or self.current
        self.errors.append({
            "line": token["line"],
            "column": token["column"],
            "message": message,
        })

    def expect(self, lexeme: str, hint: str = "") -> dict:
        if self.at(lexeme):
            return self.advance()
        self.error(f"缺少 {lexeme!r}{('（' + hint + '）') if hint else ''}")
        raise ParseError(f"缺少 {lexeme}", self.current["line"], self.current["column"])

    def expect_ident(self) -> dict:
        token = self.current
        if token["kind"] == "标识符":
            return self.advance()
        self.error(f"这里需要标识符，实际读到 {token['lexeme']!r}", token)
        raise ParseError("需要标识符", token["line"], token["column"])

    def expect_type(self) -> dict:
        """类型位置允许类型关键字（int/real/...）或自定义类型名。"""
        token = self.current
        if token["kind"] == "标识符" or token["lexeme"] in TYPE_NAMES:
            return self.advance()
        self.error(f"这里需要类型名，实际读到 {token['lexeme']!r}", token)
        raise ParseError("需要类型名", token["line"], token["column"])

    # ---------------- 语法规则 ----------------
    def parse_program(self) -> dict:
        body = []
        while self.current["kind"] != "文件结束":
            before = self.pos
            try:
                body.append(self.parse_function())
            except ParseError:
                if self.pos == before:
                    self.advance()
        return {"type": "Program", "body": body, "line": 1}

    def parse_function(self) -> dict:
        self.expect("fn", "函数定义以 fn 开头")
        return_type = self.expect_type()["lexeme"]
        name = self.expect_ident()["lexeme"]
        self.expect("(", "函数名后跟参数列表")
        params = []
        while not self.at(")"):
            ptype = self.expect_type()["lexeme"]
            pname = self.expect_ident()["lexeme"]
            params.append({"type": ptype, "name": pname})
            if not self.at(","):
                break
            self.advance()
        self.expect(")", "参数列表以 ) 结束")
        body = self.parse_block()
        return {
            "type": "FunctionDef", "name": name, "returnType": return_type,
            "params": params, "body": body, "line": body["line"],
        }

    def parse_block(self) -> dict:
        opening = self.expect("{", "语句块以 { 开始")
        statements = []
        while not self.at("}") and self.current["kind"] != "文件结束":
            before = self.pos
            try:
                statements.append(self.parse_statement())
            except ParseError:
                self.recover()
                if self.pos == before:
                    self.advance()
        if self.at("}"):
            self.advance()
        else:
            self.error("语句块缺少配对的 }", opening)
        return {"type": "Block", "body": statements, "line": opening["line"]}

    def recover(self) -> None:
        """恐慌模式恢复：跳到分号或块结束。"""
        depth = 0
        while self.current["kind"] != "文件结束":
            if self.at("{"):
                depth += 1
            elif self.at("}"):
                if depth == 0:
                    return
                depth -= 1
            elif self.at(";") and depth == 0:
                self.advance()
                return
            self.advance()

    def parse_statement(self) -> dict:
        token = self.current
        if self.at("let"):
            return self.parse_let()
        if self.at("if"):
            return self.parse_if()
        if self.at("while"):
            return self.parse_while()
        if self.at("return"):
            return self.parse_return()
        if self.at("{"):
            return self.parse_block()
        expr = self.parse_expression()
        self.expect(";", "表达式语句以分号结尾")
        return {"type": "ExprStmt", "expr": expr, "line": token["line"]}

    def parse_let(self) -> dict:
        token = self.advance()
        name = self.expect_ident()["lexeme"]
        declared = None
        if self.at(":"):
            self.advance()
            declared = self.expect_type()["lexeme"]
        value = None
        if self.at("="):
            self.advance()
            value = self.parse_expression()
        self.expect(";", "变量声明以分号结尾")
        return {"type": "Let", "name": name, "declared": declared,
                "value": value, "line": token["line"]}

    def parse_if(self) -> dict:
        token = self.advance()
        self.expect("(", "if 条件需要圆括号")
        condition = self.parse_expression()
        self.expect(")", "条件表达式以 ) 结束")
        then_branch = self.parse_statement()
        else_branch = None
        if self.at("else"):
            self.advance()
            else_branch = self.parse_statement()
        return {"type": "If", "condition": condition, "then": then_branch,
                "else": else_branch, "line": token["line"]}

    def parse_while(self) -> dict:
        token = self.advance()
        self.expect("(", "while 条件需要圆括号")
        condition = self.parse_expression()
        self.expect(")", "条件表达式以 ) 结束")
        body = self.parse_statement()
        return {"type": "While", "condition": condition, "body": body,
                "line": token["line"]}

    def parse_return(self) -> dict:
        token = self.advance()
        value = None
        if not self.at(";"):
            value = self.parse_expression()
        self.expect(";", "return 以分号结尾")
        return {"type": "Return", "value": value, "line": token["line"]}

    # ---------------- 表达式 ----------------
    def parse_expression(self) -> dict:
        return self.parse_binary(0)

    def parse_binary(self, level: int) -> dict:
        levels = (("||",), ("&&",), ("==", "!="), ("<", "<=", ">", ">="),
                  ("+", "-"), ("*", "/", "%"))
        if level >= len(levels):
            return self.parse_unary()
        left = self.parse_binary(level + 1)
        while self.current["kind"] == "运算符" and self.current["lexeme"] in levels[level]:
            op = self.advance()
            right = self.parse_binary(level + 1)
            left = {"type": "Binary", "op": op["lexeme"], "left": left,
                    "right": right, "line": op["line"]}
        return left

    def parse_unary(self) -> dict:
        token = self.current
        if token["kind"] == "运算符" and token["lexeme"] in ("-", "!"):
            self.advance()
            operand = self.parse_unary()
            return {"type": "Unary", "op": token["lexeme"], "operand": operand,
                    "line": token["line"]}
        return self.parse_primary()

    def parse_primary(self) -> dict:
        token = self.current
        if token["kind"] in ("整数", "实数", "字符串"):
            self.advance()
            return {"type": "Literal", "value": token["lexeme"], "line": token["line"]}
        if token["lexeme"] in ("true", "false"):
            self.advance()
            return {"type": "Literal", "value": token["lexeme"], "line": token["line"]}
        if token["kind"] == "标识符":
            self.advance()
            node = {"type": "Identifier", "name": token["lexeme"], "line": token["line"]}
            if self.at("("):
                self.advance()
                args = []
                while not self.at(")"):
                    args.append(self.parse_expression())
                    if not self.at(","):
                        break
                    self.advance()
                self.expect(")", "参数列表以 ) 结束")
                node = {"type": "Call", "callee": token["lexeme"], "args": args,
                        "line": token["line"]}
            return node
        if self.at("("):
            self.advance()
            inner = self.parse_expression()
            self.expect(")", "括号表达式以 ) 结束")
            return inner
        self.error(f"表达式位置出现非法记号 {token['lexeme']!r}", token)
        raise ParseError("非法表达式", token["line"], token["column"])


def parse(source: str) -> dict:
    """分析源码，返回 ``{"ast": 语法树, "errors": 错误列表}``。"""
    try:
        tokens = tokenize(source)
    except LexError as exc:
        line, column = 1, 1
        parts = str(exc).split()
        for i, part in enumerate(parts):
            if part == "第" and i + 1 < len(parts) and parts[i + 1].isdigit():
                line = int(parts[i + 1])
            if part == "行第" and i + 1 < len(parts) and parts[i + 1].isdigit():
                column = int(parts[i + 1])
        return {"ast": None, "errors": [{"line": line, "column": column,
                                         "message": str(exc)}]}
    parser = Parser(tokens)
    try:
        ast = parser.parse_program()
    except ParseError as exc:
        if not parser.errors:
            parser.errors.append(
                {"line": exc.line, "column": exc.column, "message": exc.message}
            )
        ast = None
    return {"ast": ast, "errors": parser.errors}


def analyze(source: str) -> dict:
    """合并接口：一次返回 tokens / ast / errors。"""
    result = parse(source)
    try:
        tokens = tokenize(source)
    except LexError:
        tokens = []
    return {"tokens": tokens, "ast": result["ast"], "errors": result["errors"]}
