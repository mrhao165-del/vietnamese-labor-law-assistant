# Pre-Week-6 gap closure

## Verdict

- Final verdict: **MANUAL_ACTION_REQUIRED**.
- Technical readiness: **READY**.
- Evidence readiness: **MANUAL_ACTION_REQUIRED**.

Không triển khai Week 6 trong đợt kiểm tra này. Production API vẫn dense-only; cấu hình benchmark Week 5 không bị wire vào API.

## Audit kết quả

- Week 1: 21/21 dòng còn pending, 0 dòng có evidence independent human.
- Evaluation: 60/60 câu chưa có independent human confirmation; toàn bộ evidence lịch sử là `ChatGPT_AI_PRE_REVIEW` (49) hoặc `ChatGPT_ASSISTED_REREVIEW` (11).
- Source metadata, dataset, corpus và Week 5 provenance checksum đều khớp.
- Selected configuration là `R2_H2_C10_O5_L512_B1`, được chọn ở DEV. TEST chỉ chạy một lần cho config đã chọn, không dùng để tuning.
- Error analysis có 10 case, gồm trường hợp reranker cải thiện và giảm rank; artefact có latency, token truncation và CPU RSS/resource usage.

## Quality gates đã chạy

| Gate | Kết quả |
|---|---|
| `uv sync` | PASS |
| `uv run ruff format --check .` | PASS — 94 files already formatted |
| `uv run ruff check .` | PASS |
| `uv run pyright` | PASS — 0 errors |
| `uv run pytest` | PASS — 77 passed, 1 third-party deprecation warning |
| Coverage | PASS — 82.40%, ngưỡng 82% |
| Ingestion reproducibility integration | PASS |
| Pre-Week-6 provenance integration | PASS |

## Đồng bộ trạng thái

Đã backup trước và chỉ hạ các trường trạng thái sau thành `PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION`; không thay đổi metric, prediction, split hay checksum benchmark.

- `evaluation/results/week3_dense_retrieval_baseline.json` — `status`.
- `evaluation/results/week3_dense_rag_baseline.json` — `status`.
- `evaluation/results/week4_retrieval_comparison.json` — `status` và `results[*].status` (5 cấu hình).
- `evaluation/results/week5_reranker_comparison.json` — `status`.
- `data/processed/reranker_manifest.json` — `benchmark_status`.

Backup nằm trong `evaluation/results/archive/pre_week6_gap_closure_20260715/`. Sau cập nhật, số active OFFICIAL/PROVISIONAL conflict là 0.

## Artefact human-review đã chuẩn bị

- Week 1 được bổ sung trực tiếp vào `docs/week1_manual_validation.csv`: review ID, dải source block, extracted text, trạng thái hiện tại và các trường human decision/evidence để trống.
- `data/evaluation/labor_law_eval_v1_human_review_packet.csv` là packet canonical cho 60 câu; giữ evidence AI hiện có riêng với toàn bộ trường quyết định con người để trống.
- Hướng dẫn thao tác: `docs/pre_week6_human_review_instructions.md`.

## Việc bắt buộc do con người thực hiện

1. Qualified reviewer hoàn tất cả 21 dòng Week 1 dựa trên DOCX gốc.
2. Qualified legal reviewer hoàn tất cả 60 dòng evaluation packet với tên thật, vai trò, thời gian ISO-8601 và evidence note.
3. Xử lý có căn cứ nguồn mọi `CORRECTED`, `REJECTED` hoặc `NEEDS_DISCUSSION`; không tự biến thành PASS.
4. Rerun các lệnh validation dưới đây và chỉ chuyển sang READY khi tất cả gate/evidence đều hợp lệ.

```powershell
uv run python scripts/apply_week3_manual_review.py --review-csv data/evaluation/labor_law_eval_v1_human_review_packet.csv
uv run python scripts/validate_week3_evaluation_dataset.py --require-human-reviewed
uv run python scripts/prepare_pre_week6_human_review_packets.py
uv run python scripts/generate_pre_week6_readiness.py --ruff PASS --pyright PASS --pytest PASS --coverage "PASS (coverage gate)" --integration PASS --provenance PASS
uv run pytest tests/integration/test_ingestion_reproducibility.py tests/integration/test_pre_week6_provenance.py
```
