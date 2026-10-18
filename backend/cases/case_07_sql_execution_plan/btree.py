"""B+ 树构建与查找路径模拟（用于演示索引查找原理）。

采用批量加载（bulk loading）方式构建 B+ 树：
- 键排序去重后按叶子容量（order-1）切分叶子节点；
- 内部节点的分隔键取右子树的最小键；
- BFS 为节点编号 node_id，根节点 level=0 向下递增。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BTreeNode:
    node_id: int
    level: int
    keys: list[int | float | str]
    is_leaf: bool
    children: list[BTreeNode] = field(default_factory=list)


def build_btree(keys: list[int | float | str], order: int = 5) -> BTreeNode:
    """批量加载构建 B+ 树并返回根节点（BFS 编号 node_id，根 level=0）。"""

    if order < 3:
        raise ValueError("B+ 树阶数至少为 3")
    unique_keys = sorted(set(keys), key=_sort_key)
    if not unique_keys:
        raise ValueError("至少需要 1 个键才能构建 B+ 树")

    capacity = order - 1
    leaf_chunks = [
        unique_keys[index : index + capacity]
        for index in range(0, len(unique_keys), capacity)
    ]
    current_level = [BTreeNode(node_id=-1, level=-1, keys=chunk, is_leaf=True) for chunk in leaf_chunks]

    while len(current_level) > 1:
        groups = [
            current_level[index : index + order]
            for index in range(0, len(current_level), order)
        ]
        if len(groups) > 1 and len(groups[-1]) == 1:
            # 末组仅有 1 个节点时合并到前一组，避免分隔键覆盖不全
            groups[-2].extend(groups[-1])
            groups.pop()
        parent_level: list[BTreeNode] = []
        for group in groups:
            separators = [child.keys[0] for child in group[1:]]
            parent_level.append(
                BTreeNode(node_id=-1, level=-1, keys=separators, is_leaf=False, children=group)
            )
        current_level = parent_level

    root = current_level[0]
    _assign_ids_and_levels(root)
    return root


def simulate_lookup(
    root: BTreeNode, key: int | float | str, numeric: bool = True
) -> tuple[bool, list[dict]]:
    """模拟一次索引查找，返回 (是否找到, 每步决策过程)。"""

    steps: list[dict] = []
    node = root
    found = False

    while True:
        decision = _describe_descent(node, key, numeric)
        steps.append(
            {
                "step": len(steps) + 1,
                "node_id": node.node_id,
                "level": node.level,
                "node_keys": list(node.keys),
                "decision": decision,
                "found": False,
            }
        )
        if node.is_leaf:
            found = any(_compare(k, key, numeric) == 0 for k in node.keys)
            steps[-1]["found"] = found
            steps[-1]["decision"] = (
                f"在叶子节点中找到键 {key}" if found else f"叶子节点中不存在键 {key}"
            )
            break
        node = _descend(node, key, numeric)

    return found, steps


def flatten_tree(root: BTreeNode) -> list[BTreeNode]:
    """按 BFS 顺序返回全部节点（node_id 即 BFS 序号）。"""

    ordered: list[BTreeNode] = []
    queue = [root]
    while queue:
        node = queue.pop(0)
        ordered.append(node)
        queue.extend(node.children)
    return ordered


def _sort_key(value: int | float | str) -> tuple[int, object]:
    return (0, value) if isinstance(value, (int, float)) else (1, str(value))


def _compare(a: int | float | str, b: int | float | str, numeric: bool) -> int:
    if numeric:
        left, right = float(a), float(b)
    else:
        left, right = str(a), str(b)
    return (left > right) - (left < right)


def _descend(node: BTreeNode, key: int | float | str, numeric: bool) -> BTreeNode:
    """内部节点下降：分隔键 i 是第 i+1 棵子树的最小键。"""

    index = 0
    while index < len(node.keys) and _compare(key, node.keys[index], numeric) >= 0:
        index += 1
    return node.children[index]


def _describe_descent(node: BTreeNode, key: int | float | str, numeric: bool) -> str:
    if node.is_leaf:
        return f"到达叶子节点，检查键 {key}"
    index = 0
    while index < len(node.keys) and _compare(key, node.keys[index], numeric) >= 0:
        index += 1
    if index == 0:
        return f"键 {key} < 分隔键 {node.keys[0]}，进入最左子节点"
    if index == len(node.keys):
        return f"键 {key} >= 分隔键 {node.keys[-1]}，进入最右子节点"
    return f"分隔键 {node.keys[index - 1]} <= 键 {key} < {node.keys[index]}，进入第 {index + 1} 个子节点"


def _assign_ids_and_levels(root: BTreeNode) -> None:
    queue: list[tuple[BTreeNode, int]] = [(root, 0)]
    next_id = 0
    while queue:
        node, level = queue.pop(0)
        node.node_id = next_id
        node.level = level
        next_id += 1
        queue.extend((child, level + 1) for child in node.children)
