---
name: legal-provenance-validator
description: Validate legal citations against the repository's canonical processed JSONL snapshot, including Điều, Khoản, Điểm, and chunk_id. Use when adding or reviewing calculator rules, MCP legal responses, or source-backed claims. Do not use Internet search, personal legal knowledge, or this skill to fill gaps outside the snapshot.
---

# Legal Provenance Validator

Validate each basis against fixed `data/processed/labor_law_clauses.jsonl`; caller input must never choose
another path.

1. Run `python .agents/skills/legal-provenance-validator/scripts/validate_legal_provenance.py` with
   `--article`, `--clause`, `--point`, and/or `--chunk-id`.
2. Report `SUPPORTED` only when supplied identifiers co-occur in canonical JSONL.
3. Report `EXTERNAL_REGULATION_REQUIRED` only for an explicit dependency outside the snapshot; preserve an
   in-corpus anchor if one exists and do not infer the external rule.
4. Report `OUT_OF_SCOPE` for a request outside this snapshot or product scope.

The validator does not browse, access a network, read secrets, or manufacture legal text. A missing record
does not prove a real-world rule does not exist.
