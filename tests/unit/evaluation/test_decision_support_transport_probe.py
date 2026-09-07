"""The transport probe is label-free, four-case bounded, and write-once."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import CaseIntakeError
from vietnamese_labor_law_assistant.decision_support.models import CaseIntakeInput, CaseIntakeResult
from vietnamese_labor_law_assistant.evaluation import decision_support_transport_probe as probe


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_probe_is_four_case_only_and_never_overwrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: bool,
) -> None:
    monkeypatch.setattr(probe, "_RUNS_ROOT", tmp_path)
    seen: list[CaseIntakeInput] = []

    class FakeExtractor:
        def __init__(self, _settings: Settings, **kwargs: object) -> None:
            self.observer = kwargs["transport_observer"]

        async def extract_with_transport_audit(self, case_input: CaseIntakeInput) -> object:
            seen.append(case_input)
            if failure:
                raise CaseIntakeError("CASE_INTAKE_PROVIDER_ERROR", boundary="fact")
            return CaseIntakeResult(facts=[], candidate_issues=[]), SimpleNamespace(
                model_dump=lambda **_: {}
            )

    monkeypatch.setattr(probe, "OpenAIStructuredCaseIntakeExtractor", FakeExtractor)

    async def sleep(_: float) -> None:
        pass

    output = tmp_path / "transport-probe-hybrid-fact-v2-offline"
    settings = Settings(
        openai_api_key=SecretStr("offline"),
        llm_provider="gemini_openai_compatible",
        openai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        llm_model="gemini-3.5-flash-lite",
        case_intake_fact_model="gemini-3.5-flash-lite",
        case_intake_issue_model="gemini-3.5-flash-lite",
    )
    report = await probe.run_transport_probe(settings, output, sleep=sleep)
    assert len(seen) == (1 if failure else 4)
    assert report["all_four_cases_completed"] is (not failure)
    assert report["old26_executed"] is False and report["release_holdout_accessed"] is False
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(FileExistsError):
        await probe.run_transport_probe(settings, output, sleep=sleep)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert len(seen) == (1 if failure else 4)
    assert [item.source_ref for item in seen] == [
        f"user_message:split-inference-dev-{i}"
        for i in (["004"] if failure else ["004", "008", "012", "006"])
    ]
