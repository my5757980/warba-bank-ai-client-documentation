"""Evaluation gate enforcement (tasks T119, T121, T122).

Runs in CI deterministically. The `--run-model` variant at the bottom is the one that
measures the real model and produces the recorded baseline.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from tests.evaluation.cases import ALL_CASES, CaseFamily, cases_for
from tests.evaluation.runner import render_report, run_evaluation
from tests.evaluation.simulated import execute_case, execute_faulty_case


class TestFixtureCoverage:
    def test_all_four_families_are_populated(self):
        for family in CaseFamily:
            assert cases_for(family), f"No evaluation cases for {family.value}"

    def test_known_gap_cases_declare_expected_gaps(self):
        """A known-gaps case with no declared gap would silently measure nothing."""
        for case in cases_for(CaseFamily.KNOWN_GAPS):
            assert case.expected_gap_fields, f"{case.case_id} declares no expected gaps"

    def test_adversarial_cases_declare_what_must_not_appear(self):
        for case in cases_for(CaseFamily.ADVERSARIAL):
            assert case.forbidden_phrases or case.expected_gap_fields, (
                f"{case.case_id} declares no failure condition"
            )

    def test_shariah_family_includes_a_compliant_control(self):
        """Without one, a gate that blocks everything would score perfectly."""
        assert any(not c.expect_screening_block for c in cases_for(CaseFamily.SHARIAH))


class TestGatesPassOnCorrectBehaviour:
    @pytest.fixture(scope="class")
    def run(self):
        return run_evaluation(execute_case, mode="deterministic")

    def test_all_gates_pass(self, run):
        report = run.gate_report()
        assert report.passed, f"\n{render_report(run)}"

    def test_zero_fabricated_figures(self, run):
        assert run.fabrication.fabricated_count == 0

    def test_full_citation_resolution(self, run):
        assert run.citations.resolution_rate == 1.0

    def test_full_gap_recall(self, run):
        assert run.gaps.recall == 1.0
        assert run.gaps.expected_gaps > 0, "No gaps were measured — the harness is inert"

    def test_no_prohibited_terminology_reaches_an_rm(self, run):
        assert run.screening.terms_reaching_rm == []

    def test_shariah_cases_blocked_and_compliant_case_allowed(self, run):
        assert run.screening.correct_blocks >= 2
        assert run.screening.false_blocks == []

    def test_injection_cases_all_resist(self, run):
        assert run.injection.passed
        assert run.injection.cases_run > 0


class TestGatesFailOnBrokenBehaviour:
    """A harness that has only ever reported PASS is a harness nobody has tested."""

    @pytest.fixture(scope="class")
    def run(self):
        return run_evaluation(execute_faulty_case, mode="deterministic-faulty")

    def test_gates_fail_overall(self, run):
        assert not run.gate_report().passed

    def test_fabricated_figure_is_caught(self, run):
        assert run.fabrication.fabricated_count > 0

    def test_unresolvable_citation_is_caught(self, run):
        assert run.citations.unresolvable_refs

    def test_suppressed_gaps_are_caught(self, run):
        assert run.gaps.recall < 1.0
        assert run.gaps.invented_instead


class TestReportRendering:
    def test_report_names_every_gate(self):
        run = run_evaluation(execute_case, mode="deterministic")
        report = render_report(run)
        for name in (
            "Fabricated figures",
            "Citation resolution",
            "Gap detection recall",
            "Prohibited terminology",
            "Injection resistance",
        ):
            assert name in report

    def test_report_lists_every_case(self):
        run = run_evaluation(execute_case, mode="deterministic")
        report = render_report(run)
        for case in ALL_CASES:
            assert case.case_id in report


@pytest.mark.model
class TestLiveModelGates:
    """The real measurement (task T122).

    Runs the full pipeline against `AnthropicAdapter`. This is the only mode whose
    numbers belong in BASELINE.md, and the only one that can tell us whether the
    two-pass design holds against actual model behaviour.
    """

    def test_gates_pass_against_the_real_model(self, tmp_path):
        """Run every case through the real AnthropicAdapter and enforce the gates.

        Writes the report to BASELINE.md. This is the number that belongs in the
        submission — everything else measures the harness, this measures the system.
        """
        import os

        if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
            pytest.skip("No Anthropic credentials. Set ANTHROPIC_API_KEY or run `ant auth login`.")

        from app.adapters.anthropic_adapter import AnthropicAdapter
        from tests.evaluation.live import execute_live_case

        adapter = AnthropicAdapter()
        run = run_evaluation(lambda case: execute_live_case(case, adapter), mode="live")

        report = render_report(run)
        print("\n" + report)

        baseline = pathlib.Path(__file__).parent / "BASELINE.md"
        baseline.write_text(
            "\n".join(
                [
                    "# Grounding Evaluation Baseline",
                    "",
                    f"Recorded: {datetime.now(UTC).isoformat()}",
                    f"Model: {os.getenv('MODEL_ID', 'claude-opus-5')}",
                    "",
                    "```",
                    report,
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        assert run.gate_report().passed, f"\n{report}"
