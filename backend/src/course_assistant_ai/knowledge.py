"""Course knowledge document loading for the AI assistant.

The assistant may be pointed at a custom Markdown or text document through
``AI_TUTOR_KNOWLEDGE_DOCUMENT``.  An invalid, missing, or empty custom document
never prevents the assistant from starting: the bundled default document is
used instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


KNOWLEDGE_DOCUMENT_ENV = "AI_TUTOR_KNOWLEDGE_DOCUMENT"
KNOWLEDGE_MAX_CHARS_ENV = "AI_TUTOR_KNOWLEDGE_MAX_CHARS"
DEFAULT_MAX_CHARS = 20_000
_MIN_MAX_CHARS = 1_000
_MAX_MAX_CHARS = 100_000

# This final in-code fallback keeps the assistant usable even if a deployment
# accidentally omits the repository's knowledge directory.
_BUILTIN_FALLBACK = """# 课程学习助手默认知识文档

本助手用于课程学习、代码理解、作业思路梳理和学习反馈。
当知识文档未覆盖某个问题时，应明确说明资料中没有直接结论，再提供通用的学习思路；不得虚构资料内容。
"""


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Resolved knowledge supplied to the model."""

    content: str
    source: str
    used_default: bool


class KnowledgeDocumentLoader:
    """Load a configured course document with a safe default fallback."""

    def __init__(
        self,
        *,
        configured_path: str | Path | None = None,
        default_path: str | Path | None = None,
        max_chars: int | None = None,
    ) -> None:
        self.backend_root = self._discover_backend_root()
        configured = configured_path
        if configured is None:
            configured = os.getenv(KNOWLEDGE_DOCUMENT_ENV, "").strip() or None
        self.configured_path = self._resolve_path(configured) if configured else None
        self.default_path = (
            self._resolve_path(default_path)
            if default_path is not None
            else self.backend_root / "knowledge" / "default.md"
        )
        self.max_chars = self._resolve_max_chars(max_chars)

    @staticmethod
    def _discover_backend_root() -> Path:
        """Find the repository backend directory in source and installed layouts."""

        source_root = Path(__file__).resolve().parents[2]
        working_root = Path.cwd().resolve()
        candidates = (
            source_root,
            working_root / "backend",
            working_root,
            Path("/app/backend"),
        )
        for candidate in candidates:
            if (candidate / "knowledge" / "default.md").is_file():
                return candidate
        return source_root

    def load(self) -> KnowledgeDocument:
        if self.configured_path is not None:
            content = self._read_nonempty(self.configured_path)
            if content is not None:
                return KnowledgeDocument(
                    content=self._truncate(content),
                    source=str(self.configured_path),
                    used_default=False,
                )

        default_content = self._read_nonempty(self.default_path)
        if default_content is not None:
            return KnowledgeDocument(
                content=self._truncate(default_content),
                source=str(self.default_path),
                used_default=True,
            )

        return KnowledgeDocument(
            content=self._truncate(_BUILTIN_FALLBACK),
            source="builtin-default",
            used_default=True,
        )

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.backend_root / path
        return path.resolve()

    def _resolve_max_chars(self, value: int | None) -> int:
        if value is None:
            raw = os.getenv(KNOWLEDGE_MAX_CHARS_ENV, "").strip()
            try:
                value = int(raw) if raw else DEFAULT_MAX_CHARS
            except ValueError:
                value = DEFAULT_MAX_CHARS
        return max(_MIN_MAX_CHARS, min(value, _MAX_MAX_CHARS))

    @staticmethod
    def _read_nonempty(path: Path) -> str | None:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return None
        return content or None

    def _truncate(self, content: str) -> str:
        if len(content) <= self.max_chars:
            return content
        return content[: self.max_chars].rstrip() + "\n\n[知识文档内容已按长度上限截断]"
