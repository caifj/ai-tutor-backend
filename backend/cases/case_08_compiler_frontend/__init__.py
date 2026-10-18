# -*- coding: utf-8 -*-
"""案例 8：迷你编译器前端（编译原理）。

注册入口按底座约定暴露 ``register_cases(registry)``；
``backend/cases/__init__.py`` 里加一行 import + 一行 register 即可接入。
"""
from __future__ import annotations

from ai_tutor_backend import CaseRegistry

from .adapter import MiniCompilerFrontendCase

__all__ = ["MiniCompilerFrontendCase", "register_cases"]


def register_cases(registry: CaseRegistry) -> None:
    """把本案例注册到底座（也可用于 AI_TUTOR_CASE_MODULES 独立加载）。"""

    registry.register(MiniCompilerFrontendCase())
