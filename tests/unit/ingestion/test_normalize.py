from vietnamese_labor_law_assistant.ingestion.normalize import (
    is_probable_header_or_footer,
    normalize_heading_text,
    normalize_legal_text,
)


def test_normalization_preserves_vietnamese_legal_text() -> None:
    text = "ĐIỀU\u00a0 5.\r\nNgười\u200b lao động  50%"
    assert normalize_legal_text(text) == "ĐIỀU 5.\nNgười lao động 50%"
    assert normalize_heading_text("  ĐIỀU 5. ") == "điều 5."


def test_normalization_uses_nfc_without_lowercasing_content() -> None:
    assert normalize_legal_text("Ca\u0301c Quyền") == "Các Quyền"


def test_header_footer_detection_is_conservative() -> None:
    assert is_probable_header_or_footer("Trang 2 / 10")
    assert not is_probable_header_or_footer("Điều 2. Phạm vi áp dụng")
