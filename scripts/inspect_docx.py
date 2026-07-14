from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

INPUT_PATH = Path("data/raw/labor_law.docx")
OUTPUT_PATH = Path("data/processed/docx_inventory.tsv")


def clean_for_tsv(text: str) -> str:
    return text.replace("\t", " ").replace("\r", " ").replace("\n", "\\n").strip()


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {INPUT_PATH}")

    document = Document(str(INPUT_PATH))
    rows = ["block_index\tblock_type\tstyle\ttext"]

    for block_index, block in enumerate(document.iter_inner_content()):
        if isinstance(block, Paragraph):
            text = clean_for_tsv(block.text)
            if not text:
                continue

            style_name = block.style.name if block.style is not None else ""
            style_name = style_name or ""
            rows.append(f"{block_index}\tparagraph\t{clean_for_tsv(style_name)}\t{text}")

        elif isinstance(block, Table):
            table_rows: list[str] = []

            for row in block.rows:
                cells = [clean_for_tsv(cell.text) for cell in row.cells]
                table_rows.append(" | ".join(cells))

            text = "\\n".join(table_rows)
            rows.append(f"{block_index}\ttable\t\t{text}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(rows), encoding="utf-8")

    print(f"Đã tạo: {OUTPUT_PATH}")
    print(f"Tổng block đã đọc: {len(rows) - 1}")


if __name__ == "__main__":
    main()
