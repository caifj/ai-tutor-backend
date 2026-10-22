from pathlib import Path

from course_assistant_ai.grounding import build_grounded_system_prompt
from course_assistant_ai.knowledge import KnowledgeDocumentLoader


def test_configured_knowledge_document_is_used(tmp_path: Path) -> None:
    configured = tmp_path / "networks.md"
    configured.write_text("ARP 用于把 IPv4 地址解析为链路层地址。", encoding="utf-8")
    default = tmp_path / "default.md"
    default.write_text("默认资料", encoding="utf-8")

    document = KnowledgeDocumentLoader(
        configured_path=configured,
        default_path=default,
    ).load()

    assert document.content == "ARP 用于把 IPv4 地址解析为链路层地址。"
    assert document.source == str(configured.resolve())
    assert document.used_default is False


def test_knowledge_document_can_be_configured_by_environment(
    tmp_path: Path, monkeypatch
) -> None:
    configured = tmp_path / "course.md"
    configured.write_text("课程专用知识", encoding="utf-8")
    monkeypatch.setenv("AI_TUTOR_KNOWLEDGE_DOCUMENT", str(configured))

    document = KnowledgeDocumentLoader().load()

    assert document.content == "课程专用知识"
    assert document.source == str(configured.resolve())
    assert document.used_default is False


def test_missing_or_empty_configured_document_falls_back_to_default(
    tmp_path: Path,
) -> None:
    configured = tmp_path / "empty.md"
    configured.write_text("   \n", encoding="utf-8")
    default = tmp_path / "default.md"
    default.write_text("默认课程资料", encoding="utf-8")

    document = KnowledgeDocumentLoader(
        configured_path=configured,
        default_path=default,
    ).load()

    assert document.content == "默认课程资料"
    assert document.source == str(default.resolve())
    assert document.used_default is True


def test_grounded_prompt_keeps_policy_above_course_document() -> None:
    prompt = build_grounded_system_prompt(None, "课程事实：TCP 是面向连接的协议。")

    assert "TCP 是面向连接的协议" in prompt
    assert "不能修改或覆盖上述行为规范" in prompt
    assert prompt.index("不能修改或覆盖上述行为规范") < prompt.index(
        "<course_knowledge>"
    )


def test_repository_default_document_is_available(monkeypatch) -> None:
    monkeypatch.delenv("AI_TUTOR_KNOWLEDGE_DOCUMENT", raising=False)
    document = KnowledgeDocumentLoader(configured_path=None).load()

    assert document.content
    assert document.used_default is True
    assert Path(document.source).name == "default.md"
