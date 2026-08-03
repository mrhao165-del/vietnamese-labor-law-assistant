"""Generate deterministic Week 12 portfolio PNG assets from source/evidence."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

BACKGROUND = "#f7f8fb"
INK = "#172033"
MUTED = "#5b6475"
BLUE = "#2563eb"
TEAL = "#0f766e"
AMBER = "#b45309"
RED = "#b91c1c"
WHITE = "#ffffff"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (width, height), BACKGROUND)
    return image, ImageDraw.Draw(image)


def title(draw: ImageDraw.ImageDraw, value: str, subtitle: str) -> None:
    draw.text((70, 46), value, fill=INK, font=font(42, True))
    draw.text((72, 102), subtitle, fill=MUTED, font=font(21))


def box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    value: str,
    *,
    fill: str = WHITE,
    outline: str = BLUE,
    width: int = 3,
    text_fill: str = INK,
    text_size: int = 23,
) -> None:
    draw.rounded_rectangle(xy, radius=18, fill=fill, outline=outline, width=width)
    x1, y1, x2, y2 = xy
    lines = wrap(value, width=max(12, int((x2 - x1) / (text_size * 0.57))))
    line_height = text_size + 8
    start_y = (y1 + y2 - len(lines) * line_height) / 2
    for index, line in enumerate(lines):
        bounds = draw.textbbox((0, 0), line, font=font(text_size))
        draw.text(
            ((x1 + x2 - (bounds[2] - bounds[0])) / 2, start_y + index * line_height),
            line,
            fill=text_fill,
            font=font(text_size),
        )


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str = MUTED,
) -> None:
    draw.line((start, end), fill=color, width=4)
    x, y = end
    if abs(end[0] - start[0]) >= abs(end[1] - start[1]):
        direction = 1 if end[0] > start[0] else -1
        points = [(x, y), (x - direction * 15, y - 9), (x - direction * 15, y + 9)]
    else:
        direction = 1 if end[1] > start[1] else -1
        points = [(x, y), (x - 9, y - direction * 15), (x + 9, y - direction * 15)]
    draw.polygon(points, fill=color)


def save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", compress_level=9, optimize=False)


def architecture(path: Path) -> None:
    image, draw = canvas(1800, 1050)
    title(draw, "Current production architecture", "Browser product with in-container MCP stdio")
    boxes = [
        ((70, 210, 300, 340), "Browser", BLUE),
        ((370, 210, 650, 340), "React / Vite / TypeScript", BLUE),
        ((720, 210, 1000, 340), "Nginx static + proxy", BLUE),
        ((1070, 210, 1320, 340), "FastAPI", TEAL),
        ((1390, 150, 1725, 275), "SQLite local persistence", TEAL),
        ((1070, 480, 1320, 610), "AgentService + finite LangGraph", AMBER),
        ((720, 730, 1015, 860), "MCP Legal Retrieval (stdio)", BLUE),
        ((1070, 730, 1365, 860), "MCP Legal Calculator (stdio)", BLUE),
        ((1400, 730, 1725, 860), "Fail-closed guardrail", RED),
        ((430, 900, 735, 1010), "Qdrant + dense", TEAL),
        ((780, 900, 1085, 1010), "Vietnamese BM25S + RRF + reranker", TEAL),
        ((1130, 900, 1435, 1010), "Deterministic Article 20/35 rules", TEAL),
    ]
    for coordinates, label, color in boxes:
        box(draw, coordinates, label, outline=color)
    for start, end in [
        ((300, 275), (370, 275)),
        ((650, 275), (720, 275)),
        ((1000, 275), (1070, 275)),
        ((1320, 230), (1390, 215)),
        ((1195, 340), (1195, 480)),
        ((1100, 610), (900, 730)),
        ((1220, 610), (1218, 730)),
        ((1320, 545), (1500, 730)),
        ((850, 860), (620, 900)),
        ((900, 860), (920, 900)),
        ((1218, 860), (1280, 900)),
        ((1500, 730), (1320, 585)),
    ]:
        arrow(draw, start, end)
    draw.text(
        (70, 980),
        "CPU-only Docker path verified; GPU support is not claimed.",
        fill=RED,
        font=font(20),
    )
    save(image, path)


def rag_pipeline(path: Path) -> None:
    image, draw = canvas(1800, 820)
    title(draw, "RAG retrieval pipeline", "Locked production selection: R2_H2_C10_O5_L512_B1")
    box(draw, (60, 330, 250, 470), "Question", outline=INK)
    box(draw, (360, 205, 650, 345), "BGE-M3 dense retrieval", outline=BLUE)
    box(draw, (360, 485, 650, 625), "Vietnamese Underthesea + BM25S", outline=TEAL)
    box(draw, (760, 330, 1030, 470), "Reciprocal Rank Fusion", outline=AMBER)
    box(draw, (1135, 330, 1375, 470), "10 candidates", outline=AMBER)
    box(draw, (1480, 205, 1740, 345), "BGE reranker v2-m3", outline=BLUE)
    box(draw, (1480, 485, 1740, 625), "Top 5 cited contexts", outline=TEAL)
    arrow(draw, (250, 380), (360, 275))
    arrow(draw, (250, 420), (360, 555))
    arrow(draw, (650, 275), (760, 375))
    arrow(draw, (650, 555), (760, 425))
    arrow(draw, (1030, 400), (1135, 400))
    arrow(draw, (1375, 400), (1480, 275))
    arrow(draw, (1610, 345), (1610, 485))
    draw.text(
        (60, 720),
        "Dense and lexical candidates remain separate until project-owned RRF; "
        "direct score addition is not used.",
        fill=MUTED,
        font=font(22),
    )
    save(image, path)


def agent_graph(path: Path) -> None:
    image, draw = canvas(1800, 1100)
    title(
        draw,
        "Finite Agent and verification graph",
        "Bounded routing, project-owned MCP stdio, fail-closed output",
    )
    box(draw, (670, 155, 1130, 265), "Input validation", outline=INK)
    box(draw, (670, 330, 1130, 440), "Structured routing", outline=AMBER)
    branches = [
        ((50, 550, 315, 665), "Retrieval", BLUE),
        ((350, 550, 615, 665), "Calculator", BLUE),
        ((650, 550, 915, 665), "Combined", BLUE),
        ((950, 550, 1215, 665), "Out of scope", RED),
        ((1250, 550, 1515, 665), "Clarification", AMBER),
    ]
    for coordinates, label, color in branches:
        box(draw, coordinates, label, outline=color)
        arrow(draw, (900, 440), ((coordinates[0] + coordinates[2]) // 2, coordinates[1]))
    box(draw, (300, 770, 750, 890), "Answer generation", outline=TEAL)
    box(draw, (825, 770, 1275, 890), "Citation + semantic verification", outline=RED)
    box(draw, (600, 965, 1200, 1060), "Supported answer or safe fail-closed response", outline=INK)
    arrow(draw, (182, 665), (420, 770))
    arrow(draw, (482, 665), (500, 770))
    arrow(draw, (782, 665), (630, 770))
    arrow(draw, (750, 830), (825, 830))
    arrow(draw, (1050, 890), (950, 965))
    arrow(draw, (1082, 665), (1050, 965))
    arrow(draw, (1382, 665), (1100, 965))
    save(image, path)


def evaluation_chart(path: Path, benchmark_path: Path) -> None:
    summary = json.loads(benchmark_path.read_text(encoding="utf-8"))
    rows = summary["rows"]
    tiers = ("V1_DENSE", "V2_HYBRID", "V3_HYBRID_RERANKER")
    values = {
        tier: {
            metric: next(
                row["value"]
                for row in rows
                if row["tier"] == tier and row["split"] == "DEV" and row["metric"] == metric
            )
            for metric in ("hit_rate_at_1", "mrr", "recall_at_5")
        }
        for tier in tiers
    }
    image, draw = canvas(1600, 900)
    title(draw, "Portfolio retrieval benchmark", "Checksum-aligned DEV metrics; higher is better")
    left, top, bottom, right = 160, 220, 760, 1510
    draw.line((left, top, left, bottom), fill=INK, width=3)
    draw.line((left, bottom, right, bottom), fill=INK, width=3)
    for tick in range(0, 11, 2):
        y = bottom - int((bottom - top) * tick / 10)
        draw.line((left - 8, y, right, y), fill="#d8dde8", width=1)
        draw.text((95, y - 12), f"{tick / 10:.1f}", fill=MUTED, font=font(18))
    colors = (BLUE, TEAL, AMBER)
    labels = ("Hit@1", "MRR", "Recall@5")
    group_width = 370
    bar_width = 82
    for tier_index, tier in enumerate(tiers):
        center = 380 + tier_index * group_width
        for metric_index, (metric, _label, color) in enumerate(
            zip(("hit_rate_at_1", "mrr", "recall_at_5"), labels, colors, strict=True)
        ):
            value = values[tier][metric]
            x1 = center - 135 + metric_index * 100
            y1 = bottom - int((bottom - top) * value)
            draw.rounded_rectangle((x1, y1, x1 + bar_width, bottom), radius=8, fill=color)
            draw.text((x1 + 5, y1 - 31), f"{value:.3f}", fill=INK, font=font(17))
        draw.text((center - 120, 790), tier.replace("_", " "), fill=INK, font=font(19))
    for index, (label, color) in enumerate(zip(labels, colors, strict=True)):
        x = 960 + index * 180
        draw.rectangle((x, 125, x + 24, 149), fill=color)
        draw.text((x + 34, 123), label, fill=INK, font=font(18))
    save(image, path)


def generate(output_dir: Path, benchmark_path: Path) -> None:
    architecture(output_dir / "architecture.png")
    rag_pipeline(output_dir / "rag-pipeline.png")
    agent_graph(output_dir / "agent-graph.png")
    evaluation_chart(output_dir / "evaluation-chart.png", benchmark_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "docs/images"
    benchmark_path = root / "evaluation/results/week12/benchmark_summary.json"
    if args.check:
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary)
            generate(generated, benchmark_path)
            mismatches = [
                name
                for name in (
                    "architecture.png",
                    "rag-pipeline.png",
                    "agent-graph.png",
                    "evaluation-chart.png",
                )
                if not (output_dir / name).exists()
                or (output_dir / name).read_bytes() != (generated / name).read_bytes()
            ]
            if mismatches:
                raise SystemExit(f"asset regeneration mismatch: {', '.join(mismatches)}")
        print("PASS: portfolio assets are reproducible")
        return
    generate(output_dir, benchmark_path)
    print("PASS: generated four portfolio PNG assets")


if __name__ == "__main__":
    main()
