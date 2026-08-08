"""Generate deterministic Week 12 portfolio PNG assets from source/evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageChops, ImageDraw, ImageFont, UnidentifiedImageError

BACKGROUND = "#f7f8fb"
INK = "#172033"
MUTED = "#5b6475"
BLUE = "#2563eb"
TEAL = "#0f766e"
AMBER = "#b45309"
RED = "#b91c1c"
WHITE = "#ffffff"

EXPECTED_ASSETS = {
    "architecture.png": (1800, 1050),
    "rag-pipeline.png": (1800, 820),
    "agent-graph.png": (1800, 1100),
    "evaluation-chart.png": (1600, 900),
}
DOCUMENTATION_SCREENSHOT_ASSETS = frozenset(
    {
        "ui-chat-citation.png",
        "ui-calculator-trace.png",
        "ui-guardrail-or-clarification.png",
        "ui-mobile-evidence.png",
    }
)
BENCHMARK_TIERS = ("V1_DENSE", "V2_HYBRID", "V3_HYBRID_RERANKER")
BENCHMARK_METRICS = ("hit_rate_at_1", "mrr", "recall_at_5")


@dataclass(frozen=True)
class DecodedImage:
    raw_sha256: str
    canonical_sha256: str
    file_size: int
    format: str
    size: tuple[int, int]
    mode: str
    rgb_bytes: bytes


@dataclass(frozen=True)
class ImageComparison:
    committed: DecodedImage
    generated: DecodedImage
    changed_pixel_count: int | None
    difference_bbox: tuple[int, int, int, int] | None
    max_per_channel_difference: int | None
    mean_absolute_channel_difference: float | None

    @property
    def matches(self) -> bool:
        return (
            self.committed.format == self.generated.format
            and self.committed.size == self.generated.size
            and self.committed.rgb_bytes == self.generated.rgb_bytes
        )

    @property
    def classification(self) -> str:
        if self.matches and self.committed.raw_sha256 != self.generated.raw_sha256:
            return "PNG_ENCODING_ONLY"
        if self.matches:
            return "EXACT_MATCH"
        return "MATERIAL_PIXEL_DIFFERENCE"


def _canonical_digest(decoded: DecodedImage) -> str:
    width, height = decoded.size
    payload = b"".join(
        (
            decoded.format.encode("ascii"),
            b"\0",
            width.to_bytes(8, "big"),
            height.to_bytes(8, "big"),
            b"RGB\0",
            decoded.rgb_bytes,
        )
    )
    return hashlib.sha256(payload).hexdigest()


def decode_image(path: Path) -> DecodedImage:
    """Decode a PNG and retain both transport and canonical pixel evidence."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"missing or unreadable image: {path}") from exc
    if not raw:
        raise ValueError(f"empty image: {path}")
    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG":
                raise ValueError(f"expected PNG image: {path}")
            rgb_bytes = image.convert("RGB").tobytes()
            decoded = DecodedImage(
                raw_sha256=hashlib.sha256(raw).hexdigest(),
                canonical_sha256="",
                file_size=len(raw),
                format=image.format,
                size=image.size,
                mode=image.mode,
                rgb_bytes=rgb_bytes,
            )
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"corrupt or undecodable PNG: {path}") from exc
    return DecodedImage(
        raw_sha256=decoded.raw_sha256,
        canonical_sha256=_canonical_digest(decoded),
        file_size=decoded.file_size,
        format=decoded.format,
        size=decoded.size,
        mode=decoded.mode,
        rgb_bytes=decoded.rgb_bytes,
    )


def canonical_image_digest(path: Path) -> str:
    """Hash PNG identity, dimensions, normalized RGB mode, and exact pixels."""

    return decode_image(path).canonical_sha256


def compare_images(committed_path: Path, generated_path: Path) -> ImageComparison:
    committed = decode_image(committed_path)
    generated = decode_image(generated_path)
    if committed.size != generated.size:
        return ImageComparison(committed, generated, None, None, None, None)

    difference = ImageChops.difference(
        Image.frombytes("RGB", committed.size, committed.rgb_bytes),
        Image.frombytes("RGB", generated.size, generated.rgb_bytes),
    )
    difference_bytes = difference.tobytes()
    changed_pixel_count = sum(
        any(difference_bytes[offset : offset + 3]) for offset in range(0, len(difference_bytes), 3)
    )
    return ImageComparison(
        committed=committed,
        generated=generated,
        changed_pixel_count=changed_pixel_count,
        difference_bbox=difference.getbbox(),
        max_per_channel_difference=max(difference_bytes, default=0),
        mean_absolute_channel_difference=(
            sum(difference_bytes) / len(difference_bytes) if difference_bytes else 0.0
        ),
    )


def load_benchmark_values(benchmark_path: Path) -> dict[str, dict[str, float]]:
    try:
        summary = json.loads(benchmark_path.read_text(encoding="utf-8"))
        rows = summary["rows"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"invalid benchmark source: {benchmark_path}") from exc

    values: dict[str, dict[str, float]] = {}
    for tier in BENCHMARK_TIERS:
        values[tier] = {}
        for metric in BENCHMARK_METRICS:
            matches = [
                row
                for row in rows
                if row.get("tier") == tier
                and row.get("split") == "DEV"
                and row.get("metric") == metric
            ]
            if len(matches) != 1:
                raise ValueError(f"benchmark must contain exactly one DEV {tier}/{metric} row")
            value = matches[0].get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"benchmark DEV {tier}/{metric} must have a numeric value")
            values[tier][metric] = float(value)
    return values


def validate_asset_directory(
    output_dir: Path, *, allow_documentation_screenshots: bool = False
) -> None:
    actual_names = {path.name for path in output_dir.glob("*.png")}
    expected_names = set(EXPECTED_ASSETS)
    allowed_extra_names = (
        set(DOCUMENTATION_SCREENSHOT_ASSETS) if allow_documentation_screenshots else set()
    )
    missing = sorted(expected_names - actual_names)
    unexpected = sorted(actual_names - expected_names - allowed_extra_names)
    if missing or unexpected:
        raise ValueError(f"portfolio PNG set mismatch; missing={missing}, unexpected={unexpected}")
    for name, expected_size in EXPECTED_ASSETS.items():
        decoded = decode_image(output_dir / name)
        if decoded.size != expected_size or decoded.mode != "RGB":
            raise ValueError(
                f"invalid portfolio asset contract for {name}: "
                f"size={decoded.size}, mode={decoded.mode}"
            )


def _print_comparison(name: str, comparison: ImageComparison, classification: str) -> None:
    committed = comparison.committed
    generated = comparison.generated
    print(
        f"- {name}:\n"
        f"  raw SHA committed/generated: "
        f"{committed.raw_sha256} / {generated.raw_sha256}\n"
        f"  canonical pixel SHA committed/generated: "
        f"{committed.canonical_sha256} / {generated.canonical_sha256}\n"
        f"  file size committed/generated: "
        f"{committed.file_size} / {generated.file_size}\n"
        f"  dimensions committed/generated: {committed.size} / {generated.size}\n"
        f"  mode committed/generated: {committed.mode} / {generated.mode}\n"
        f"  changed pixels: {comparison.changed_pixel_count}\n"
        f"  difference bbox: {comparison.difference_bbox}\n"
        f"  maximum per-channel difference: {comparison.max_per_channel_difference}\n"
        f"  mean absolute channel difference: "
        f"{comparison.mean_absolute_channel_difference}\n"
        f"  classification: {classification}"
    )


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
    values = load_benchmark_values(benchmark_path)
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
    for tier_index, tier in enumerate(BENCHMARK_TIERS):
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
            try:
                load_benchmark_values(benchmark_path)
                generate(generated, benchmark_path)
                validate_asset_directory(generated)
            except ValueError as exc:
                raise SystemExit(f"portfolio asset contract failure: {exc}") from exc

            contract_error: str | None = None
            try:
                validate_asset_directory(output_dir, allow_documentation_screenshots=True)
            except ValueError as exc:
                contract_error = str(exc)

            mismatches: list[tuple[str, ImageComparison]] = []
            invalid_images: list[tuple[str, str]] = []
            for name in EXPECTED_ASSETS:
                try:
                    comparison = compare_images(output_dir / name, generated / name)
                except ValueError as exc:
                    invalid_images.append((name, str(exc)))
                    continue
                if not comparison.matches:
                    mismatches.append((name, comparison))
                elif (
                    comparison.committed.size != EXPECTED_ASSETS[name]
                    or comparison.committed.mode != "RGB"
                ):
                    mismatches.append((name, comparison))
            if contract_error or mismatches or invalid_images:
                print("portfolio asset check failure:")
                if contract_error:
                    print(f"contract: {contract_error}")
                for name, comparison in mismatches:
                    classification = (
                        comparison.classification
                        if not comparison.matches
                        else "MATERIAL_PIXEL_DIFFERENCE"
                    )
                    _print_comparison(name, comparison, classification)
                for name, error in invalid_images:
                    print(
                        f"- {name}:\n"
                        f"  raw SHA committed/generated: unavailable\n"
                        f"  canonical pixel SHA committed/generated: unavailable\n"
                        f"  file size and mode: unavailable\n"
                        f"  changed pixels: unavailable\n"
                        f"  difference bbox: unavailable\n"
                        f"  classification: MATERIAL_PIXEL_DIFFERENCE\n"
                        f"  error: {error}"
                    )
                raise SystemExit(1)
        print("PASS: portfolio assets are reproducible")
        return
    generate(output_dir, benchmark_path)
    print("PASS: generated four portfolio PNG assets")


if __name__ == "__main__":
    main()
