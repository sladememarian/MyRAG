"""Live provider test. Skipped by default; run with: pytest -m live"""
import os

import pytest

from rag.chain import answer_question

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ITERACOMPUTE_API_KEY")),
        reason="no provider API key is set",
    ),
]


@pytest.mark.django_db
def test_live_llm_answers_in_persian(indexed_document, settings):
    """Requirement: answers are produced by a real configured provider model."""
    settings.RETRIEVAL_USE_MULTI_QUERY = False  # one model call keeps free quota

    result = answer_question("جنگل چیست؟")

    assert result["answer"].strip()
    assert result["sources"]
