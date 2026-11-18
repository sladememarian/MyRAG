"""Tests for the `ask` management command."""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_ask_command_prints_answer(monkeypatch, capsys):
    """Requirement: the chain can be tested from the terminal."""
    monkeypatch.setattr(
        "qa.management.commands.ask.answer_question",
        lambda question: {
            "answer": "پاسخ ترمینال",
            "sources": [
                {
                    "document_id": 1,
                    "title": "سند",
                    "chunk_index": 0,
                    "score": 0.75,
                    "snippet": "بخش",
                }
            ],
        },
    )

    call_command("ask", "جنگل چیست؟")

    output = capsys.readouterr().out
    assert "پاسخ ترمینال" in output
    assert "سند" in output


def test_ask_command_reports_rag_errors(monkeypatch):
    """Requirement: CLI errors are clear, not stack traces."""
    from rag.errors import NoRelevantContentError

    def fail(question):
        raise NoRelevantContentError("مطلبی پیدا نشد")

    monkeypatch.setattr("qa.management.commands.ask.answer_question", fail)

    with pytest.raises(CommandError, match="مطلبی پیدا نشد"):
        call_command("ask", "سوال")
