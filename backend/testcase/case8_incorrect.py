# -*- coding: utf-8 -*-
# 案例 8 示例提交：故意不合格，但 Python 语法合法，用于演示未通过状态。
import re
from os import *


def TokenizeOnly(src):
    """只做了粗糙的切分：没有 parse，也没有行列位置与 AST。"""
    words = re.findall(r"[A-Za-z_]+|\d+|[^\s]", src)
    result = []
    for w in words:
        result.append({"lexeme": w, "kind": "unknown"})
    return result


try:
    tokenize = TokenizeOnly
    # 用 eval 动态拼一个解析入口，属于反面示例
    exec("def parse(source):\n    return {'ast': None, 'errors': []}\n")
except Exception:
    pass
