"""Vietnamese legal QA prompt construction isolated from HTTP handling."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vietnamese_labor_law_assistant.retrieval.models import RetrievedChunk


@dataclass(frozen=True)
class PromptPackage:
    system: str
    user: str
    context_map: dict[str, RetrievedChunk]


SYSTEM_INSTRUCTION = """Bạn là trợ lý hỗ trợ tra cứu Bộ luật Lao động Việt Nam.
Chỉ sử dụng thông tin trong các context được cung cấp. Không dùng kiến thức bên ngoài để
khẳng định nội dung pháp luật, không tự tạo số Điều, Khoản hoặc Điểm. Mỗi claim pháp lý
phải có ít nhất một context_id hợp lệ trong prompt. Nếu context không đủ, đặt
insufficient_context=true, giải thích ngắn gọn và không suy đoán. Bạn không phải luật sư
và không thay thế cơ quan có thẩm quyền. Trả lời bằng tiếng Việt, rõ ràng, ngắn gọn; không
sao chép toàn bộ Điều luật khi chỉ cần tóm tắt."""


def _context_text(context_id: str, chunk: RetrievedChunk) -> str:
    lines = [f"[{context_id}]", f"Văn bản: {chunk.document_name}"]
    if chunk.chapter_number:
        lines.append(
            f"Chương: {chunk.chapter_number}"
            + (f" - {chunk.chapter_title}" if chunk.chapter_title else "")
        )
    if chunk.section_number:
        lines.append(
            f"Mục: {chunk.section_number}"
            + (f" - {chunk.section_title}" if chunk.section_title else "")
        )
    article = f"Điều: {chunk.article_number}" + (
        f" - {chunk.article_title}" if chunk.article_title else ""
    )
    lines.append(article)
    if chunk.clause_number:
        lines.append(f"Khoản: {chunk.clause_number}")
    if chunk.point_label:
        lines.append(f"Điểm: {chunk.point_label}")
    elif chunk.point_labels:
        lines.append(f"Điểm: {', '.join(chunk.point_labels)}")
    lines.extend(["Nội dung:", chunk.content])
    return "\n".join(lines)


def build_legal_qa_prompt(question: str, contexts: Sequence[RetrievedChunk]) -> PromptPackage:
    """Build a stable prompt package and server-owned context-id mapping."""
    context_map = {f"CTX-{index:03d}": chunk for index, chunk in enumerate(contexts, start=1)}
    body = "\n\n".join(
        _context_text(context_id, chunk) for context_id, chunk in context_map.items()
    )
    user = f"Câu hỏi: {question}\n\nContexts:\n{body}\n\nTrả về JSON theo schema đã yêu cầu."
    return PromptPackage(system=SYSTEM_INSTRUCTION, user=user, context_map=context_map)
