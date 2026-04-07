"""Router nhẹ: chào hỏi / meta — không gọi RAG."""

from __future__ import annotations


def route_smalltalk(question: str) -> str | None:
    q = (question or "").strip().lower()
    if len(q) < 2:
        return None

    exact = {
        "xin chào",
        "chào",
        "chao",
        "hello",
        "hi",
        "hey",
        "cảm ơn",
        "cam on",
        "thanks",
        "thank you",
    }
    if q in exact:
        return _GREETING_REPLY

    prefixes = (
        "xin chào ",
        "chào ",
        "chao ",
        "hello ",
        "hi ",
        "hey ",
        "cảm ơn ",
        "cam on ",
    )
    if any(q.startswith(p) for p in prefixes) and len(q) < 80:
        return _GREETING_REPLY

    if "bạn là ai" in q or "ban la ai" in q or "you are" in q:
        return _WHO_REPLY

    return None


_GREETING_REPLY = (
    "Xin chào. Tôi là trợ lý pháp lý demo, trả lời dựa trên văn bản luật đã được đưa vào hệ thống. "
    "Bạn hãy đặt câu hỏi cụ thể về nội dung luật (ví dụ giao thông đường bộ, điều kiện vận tải, …)."
)

_WHO_REPLY = (
    "Tôi là chatbot RAG demo: truy xuất các đoạn văn bản luật liên quan rồi tóm tắt trả lời. "
    "Tôi không thay thế tư vấn pháp lý chính thức."
)
