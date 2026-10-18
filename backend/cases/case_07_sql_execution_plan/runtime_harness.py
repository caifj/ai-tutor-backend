"""案例7 运行时测试夹具（在沙箱中运行学生代码并验证功能）。"""

HARNESS_SOURCE = r'''
import json
import runpy

MARKER = "__AI_TUTOR_CASE7_RESULT__"

try:
    submitted = runpy.run_path("student.py")
    load_error = None
except BaseException as exc:
    submitted = {}
    load_error = "{0}: {1}".format(type(exc).__name__, exc)


def test_parse_explain():
    """测试执行计划解析功能。"""
    checks = []

    # 测试数据：MySQL EXPLAIN 输出
    mysql_plan = """ -> id=1, select_type=SIMPLE, table=orders, type=ALL, possible_keys=NULL, key=NULL, rows=59, Extra=Using where
 -> id=2, select_type=SIMPLE, table=users, type=ref, possible_keys=idx_user_id, key=idx_user_id, rows=5, Extra=NULL"""

    try:
        # 调用学生实现的 parse_explain
        parse_explain = submitted.get("parse_explain")
        if not callable(parse_explain):
            raise AssertionError("未找到 parse_explain 函数")
        result = parse_explain(mysql_plan)

        # 验证返回类型
        if isinstance(result, dict):
            checks.append({
                "check_id": "PARSE_EXPLAIN_TYPE",
                "title": "parse_explain 返回字典类型",
                "passed": True,
                "evidence": f"返回类型：{type(result).__name__}",
            })
        else:
            checks.append({
                "check_id": "PARSE_EXPLAIN_TYPE",
                "title": "parse_explain 返回字典类型",
                "passed": False,
                "evidence": f"返回类型：{type(result).__name__}，期望：dict",
            })

        # 验证是否包含必要字段
        required_fields = ["nodes", "index_usage", "full_scan_findings"]
        missing_fields = [f for f in required_fields if f not in result]
        if not missing_fields:
            checks.append({
                "check_id": "PARSE_EXPLAIN_FIELDS",
                "title": "返回结果包含必要字段",
                "passed": True,
                "evidence": f"包含字段：{', '.join(required_fields)}",
            })
        else:
            checks.append({
                "check_id": "PARSE_EXPLAIN_FIELDS",
                "title": "返回结果包含必要字段",
                "passed": False,
                "evidence": f"缺少字段：{', '.join(missing_fields)}",
            })

        # 验证全表扫描检测
        if "full_scan_findings" in result:
            findings = result["full_scan_findings"]
            if isinstance(findings, list) and len(findings) > 0:
                checks.append({
                    "check_id": "FULL_SCAN_DETECTION",
                    "title": "检测到全表扫描",
                    "passed": True,
                    "evidence": f"检测到 {len(findings)} 处全表扫描",
                })
            else:
                checks.append({
                    "check_id": "FULL_SCAN_DETECTION",
                    "title": "检测到全表扫描",
                    "passed": False,
                    "evidence": "未检测到全表扫描（type=ALL）",
                })

    except Exception as exc:
        checks.append({
            "check_id": "PARSE_EXPLAIN_ERROR",
            "title": "parse_explain 执行无异常",
            "passed": False,
            "evidence": f"执行出错：{str(exc)}",
        })

    return checks


def test_btree():
    """测试 B+ 树构建和查找功能。"""
    checks = []

    try:
        # 测试数据
        keys = [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
        lookup_key = 25

        # 调用学生实现的 build_btree
        build_btree = submitted.get("build_btree")
        if not callable(build_btree):
            raise AssertionError("未找到 build_btree 函数")
        tree = build_btree(keys, order=3)

        # 验证返回类型
        if tree is not None:
            checks.append({
                "check_id": "BUILD_BTREE",
                "title": "build_btree 成功构建 B+ 树",
                "passed": True,
                "evidence": f"返回类型：{type(tree).__name__}",
            })
        else:
            checks.append({
                "check_id": "BUILD_BTREE",
                "title": "build_btree 成功构建 B+ 树",
                "passed": False,
                "evidence": "返回 None",
            })
            return checks

        # 调用学生实现的 lookup
        if hasattr(tree, 'lookup'):
            path = tree.lookup(lookup_key)
        elif callable(submitted.get('lookup')):
            lookup = submitted["lookup"]
            path = lookup(tree, lookup_key)
        else:
            checks.append({
                "check_id": "LOOKUP_EXISTS",
                "title": "实现查找功能",
                "passed": False,
                "evidence": "未找到 lookup 方法或函数",
            })
            return checks

        # 验证查找路径
        if isinstance(path, (list, tuple)) and len(path) > 0:
            checks.append({
                "check_id": "LOOKUP_PATH",
                "title": "返回查找路径",
                "passed": True,
                "evidence": f"路径长度：{len(path)}",
            })

            # 验证是否找到键
            found = any(lookup_key in (node if isinstance(node, (list, tuple)) else [node]) for node in path)
            if found or path[-1] == lookup_key:
                checks.append({
                    "check_id": "LOOKUP_FOUND",
                    "title": "正确找到目标键",
                    "passed": True,
                    "evidence": f"在路径中找到键 {lookup_key}",
                })
            else:
                checks.append({
                    "check_id": "LOOKUP_FOUND",
                    "title": "正确找到目标键",
                    "passed": False,
                    "evidence": f"未在路径中找到键 {lookup_key}",
                })
        else:
            checks.append({
                "check_id": "LOOKUP_PATH",
                "title": "返回查找路径",
                "passed": False,
                "evidence": f"返回类型：{type(path).__name__}，期望：list/tuple",
            })

    except Exception as exc:
        checks.append({
            "check_id": "BTREE_ERROR",
            "title": "B+ 树操作执行无异常",
            "passed": False,
            "evidence": f"执行出错：{str(exc)}",
        })

    return checks


def main():
    """主测试函数。"""
    all_checks = []

    if load_error:
        all_checks.append({
            "check_id": "STUDENT_CODE_LOAD",
            "title": "学生代码加载成功",
            "passed": False,
            "evidence": load_error,
        })
        result = {
            "checks": all_checks,
            "observations": {"load_error": load_error},
        }
        print(f"{MARKER}{json.dumps(result)}")
        return

    # 测试执行计划解析
    all_checks.extend(test_parse_explain())

    # 测试 B+ 树
    all_checks.extend(test_btree())

    # 输出结果
    result = {
        "checks": all_checks,
        "observations": {
            "total_checks": len(all_checks),
            "passed_checks": sum(1 for c in all_checks if c.get("passed")),
        }
    }

    print(f"{MARKER}{json.dumps(result)}")


if __name__ == "__main__":
    main()
'''
