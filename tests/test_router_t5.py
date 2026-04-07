"""T5: router chào hỏi không cần RAG."""

from __future__ import annotations

from tools.chat_router import route_smalltalk


def test_t5_greeting_returns_fixed_reply() -> None:
    assert route_smalltalk("xin chào") is not None
    assert route_smalltalk("Xin chào bạn") is not None
    r = route_smalltalk("bạn là ai")
    assert r is not None
    assert "RAG" in r or "chatbot" in r.lower() or "trợ lý" in r.lower()


def test_normal_legal_question_not_routed() -> None:
    assert route_smalltalk("điều kiện kinh doanh vận tải bằng xe ô tô") is None
