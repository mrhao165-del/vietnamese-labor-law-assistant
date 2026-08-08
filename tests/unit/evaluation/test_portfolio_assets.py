from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def _load_generator() -> ModuleType:
    path = ROOT / "scripts/generate_portfolio_assets.py"
    spec = importlib.util.spec_from_file_location("portfolio_asset_generator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


assets = _load_generator()


def _save(path: Path, image: Image.Image, *, compress_level: int = 9) -> None:
    image.save(path, format="PNG", compress_level=compress_level, optimize=False)


def test_identical_pixels_with_different_compression_pass(tmp_path: Path) -> None:
    pixels = [((index * 17) % 256, (index * 31) % 256, (index * 47) % 256) for index in range(4096)]
    image = Image.new("RGB", (64, 64))
    image.putdata(pixels)
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _save(first, image, compress_level=0)
    _save(second, image, compress_level=9)

    comparison = assets.compare_images(first, second)

    assert first.read_bytes() != second.read_bytes()
    assert comparison.matches
    assert comparison.classification == "PNG_ENCODING_ONLY"
    assert comparison.changed_pixel_count == 0


def test_one_pixel_change_fails(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _save(first, Image.new("RGB", (4, 4), (10, 20, 30)))
    changed = Image.new("RGB", (4, 4), (10, 20, 30))
    changed.putpixel((2, 1), (10, 20, 31))
    _save(second, changed)

    comparison = assets.compare_images(first, second)

    assert not comparison.matches
    assert comparison.changed_pixel_count == 1
    assert comparison.difference_bbox == (2, 1, 3, 2)
    assert comparison.classification == "MATERIAL_PIXEL_DIFFERENCE"


def test_dimension_change_fails(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _save(first, Image.new("RGB", (4, 4), "white"))
    _save(second, Image.new("RGB", (5, 4), "white"))

    comparison = assets.compare_images(first, second)

    assert not comparison.matches
    assert comparison.changed_pixel_count is None
    assert comparison.classification == "MATERIAL_PIXEL_DIFFERENCE"


def test_mode_difference_that_changes_normalized_pixels_fails(tmp_path: Path) -> None:
    rgb_path = tmp_path / "rgb.png"
    grayscale_path = tmp_path / "grayscale.png"
    _save(rgb_path, Image.new("RGB", (3, 3), (10, 20, 30)))
    _save(grayscale_path, Image.new("L", (3, 3), 10))

    comparison = assets.compare_images(rgb_path, grayscale_path)

    assert not comparison.matches
    assert comparison.committed.mode == "RGB"
    assert comparison.generated.mode == "L"


def test_missing_image_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing or unreadable image"):
        assets.canonical_image_digest(tmp_path / "missing.png")


def test_corrupt_png_fails(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not a PNG")

    with pytest.raises(ValueError, match="corrupt or undecodable PNG"):
        assets.canonical_image_digest(corrupt)


def test_asset_directory_requires_exact_expected_png_set(tmp_path: Path) -> None:
    for name, size in assets.EXPECTED_ASSETS.items():
        _save(tmp_path / name, Image.new("RGB", size, "white"))
    _save(tmp_path / "unexpected.png", Image.new("RGB", (1, 1), "white"))

    with pytest.raises(ValueError, match="PNG set mismatch"):
        assets.validate_asset_directory(tmp_path, allow_documentation_screenshots=True)


def test_asset_directory_allows_documented_ui_screenshots(tmp_path: Path) -> None:
    for name, size in assets.EXPECTED_ASSETS.items():
        _save(tmp_path / name, Image.new("RGB", size, "white"))
    _save(tmp_path / "ui-chat-citation.png", Image.new("RGB", (1, 1), "white"))

    assets.validate_asset_directory(tmp_path, allow_documentation_screenshots=True)


@pytest.mark.parametrize("mode", ["L", "RGBA"])
def test_asset_directory_requires_rgb_mode(tmp_path: Path, mode: str) -> None:
    for name, size in assets.EXPECTED_ASSETS.items():
        image_mode = mode if name == "architecture.png" else "RGB"
        _save(tmp_path / name, Image.new(image_mode, size))

    with pytest.raises(ValueError, match="invalid portfolio asset contract"):
        assets.validate_asset_directory(tmp_path)


def test_asset_directory_requires_declared_dimensions(tmp_path: Path) -> None:
    for name, size in assets.EXPECTED_ASSETS.items():
        actual_size = (size[0] - 1, size[1]) if name == "agent-graph.png" else size
        _save(tmp_path / name, Image.new("RGB", actual_size, "white"))

    with pytest.raises(ValueError, match="invalid portfolio asset contract"):
        assets.validate_asset_directory(tmp_path)


def test_benchmark_contract_requires_every_dev_metric(tmp_path: Path) -> None:
    benchmark_path = ROOT / "evaluation/results/week12/benchmark_summary.json"
    summary = json.loads(benchmark_path.read_text(encoding="utf-8"))
    summary["rows"] = [
        row
        for row in summary["rows"]
        if not (row["tier"] == "V2_HYBRID" and row["split"] == "DEV" and row["metric"] == "mrr")
    ]
    incomplete = tmp_path / "benchmark.json"
    incomplete.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one DEV V2_HYBRID/mrr"):
        assets.load_benchmark_values(incomplete)


def test_benchmark_contract_rejects_non_numeric_metric(tmp_path: Path) -> None:
    benchmark_path = ROOT / "evaluation/results/week12/benchmark_summary.json"
    summary = json.loads(benchmark_path.read_text(encoding="utf-8"))
    row = next(
        row
        for row in summary["rows"]
        if row["tier"] == "V3_HYBRID_RERANKER"
        and row["split"] == "DEV"
        and row["metric"] == "recall_at_5"
    )
    row["value"] = None
    invalid = tmp_path / "benchmark.json"
    invalid.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="must have a numeric value"):
        assets.load_benchmark_values(invalid)


def test_all_current_portfolio_assets_pass_canonical_check(tmp_path: Path) -> None:
    benchmark_path = ROOT / "evaluation/results/week12/benchmark_summary.json"
    values = assets.load_benchmark_values(benchmark_path)
    assets.validate_asset_directory(ROOT / "docs/images", allow_documentation_screenshots=True)
    assets.generate(tmp_path, benchmark_path)
    assets.validate_asset_directory(tmp_path)

    assert set(values) == set(assets.BENCHMARK_TIERS)
    assert all(set(metrics) == set(assets.BENCHMARK_METRICS) for metrics in values.values())
    assert all(
        assets.compare_images(ROOT / "docs/images" / name, tmp_path / name).matches
        for name in assets.EXPECTED_ASSETS
    )
