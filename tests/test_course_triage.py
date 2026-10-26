"""Tests for course_triage module."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from course_triage import SCENARIOS, grade_triage


class TestScenarios(unittest.TestCase):
    """Sanity checks on scenario structure."""

    def test_exactly_seven_scenarios(self):
        """There are exactly 7 scenarios."""
        self.assertEqual(len(SCENARIOS), 7)

    def test_scenario_ids(self):
        """Scenario ids are a through g."""
        ids = [s['id'] for s in SCENARIOS]
        self.assertEqual(ids, ['a', 'b', 'c', 'd', 'e', 'f', 'g'])

    def test_all_scenarios_have_required_fields(self):
        """Every scenario has all required fields."""
        required_fields = {'id', 'title', 'context', 'output', 'decision',
                          'facts', 'required', 'wrong', 'explanation'}
        for scenario in SCENARIOS:
            self.assertEqual(set(scenario.keys()), required_fields,
                           f"Scenario {scenario['id']} missing fields")

    def test_facts_have_key_and_text(self):
        """Every fact is a (key, text) tuple."""
        for scenario in SCENARIOS:
            for fact in scenario['facts']:
                self.assertEqual(len(fact), 2)
                self.assertIsInstance(fact[0], str)
                self.assertIsInstance(fact[1], str)

    def test_required_and_wrong_are_sets(self):
        """Required and wrong are sets."""
        for scenario in SCENARIOS:
            self.assertIsInstance(scenario['required'], set)
            self.assertIsInstance(scenario['wrong'], set)

    def test_required_and_wrong_keys_exist(self):
        """All required and wrong keys exist in facts."""
        for scenario in SCENARIOS:
            fact_keys = {k for k, _ in scenario['facts']}
            for key in scenario['required']:
                self.assertIn(key, fact_keys,
                            f"Scenario {scenario['id']}: required key '{key}' not in facts")
            for key in scenario['wrong']:
                self.assertIn(key, fact_keys,
                            f"Scenario {scenario['id']}: wrong key '{key}' not in facts")

    def test_required_and_wrong_no_overlap(self):
        """Required and wrong sets don't overlap."""
        for scenario in SCENARIOS:
            overlap = scenario['required'] & scenario['wrong']
            self.assertEqual(overlap, set(),
                           f"Scenario {scenario['id']}: required and wrong overlap: {overlap}")

    def test_decision_is_valid(self):
        """Decision is 'stop' or 'continue'."""
        for scenario in SCENARIOS:
            self.assertIn(scenario['decision'], {'stop', 'continue'},
                         f"Scenario {scenario['id']}: invalid decision '{scenario['decision']}'")

    def test_at_least_two_continue_scenarios(self):
        """At least 2 scenarios have decision 'continue'."""
        continue_count = sum(1 for s in SCENARIOS if s['decision'] == 'continue')
        self.assertGreaterEqual(continue_count, 2)


class TestGradeTriage(unittest.TestCase):
    """Tests for grade_triage function."""

    def test_correct_answer_passes(self):
        """Correct decision + all required facts = pass."""
        for scenario in SCENARIOS:
            result = grade_triage(
                scenario['id'],
                scenario['decision'],
                scenario['required']
            )
            self.assertTrue(result['passed'],
                          f"Scenario {scenario['id']}: correct answer should pass")

    def test_wrong_decision_fails(self):
        """Wrong decision = fail."""
        for scenario in SCENARIOS:
            wrong_decision = 'continue' if scenario['decision'] == 'stop' else 'stop'
            result = grade_triage(
                scenario['id'],
                wrong_decision,
                scenario['required']
            )
            self.assertFalse(result['passed'],
                           f"Scenario {scenario['id']}: wrong decision should fail")

    def test_no_decision_fails(self):
        """No decision (None or empty) = fail."""
        scenario = SCENARIOS[0]
        for no_decision in [None, '']:
            result = grade_triage(
                scenario['id'],
                no_decision,
                scenario['required']
            )
            self.assertFalse(result['passed'],
                           f"Scenario {scenario['id']}: no decision should fail")

    def test_missing_required_fact_fails(self):
        """Missing a required fact = fail."""
        for scenario in SCENARIOS:
            if not scenario['required']:
                # Skip scenarios with no required facts
                continue
            required_list = list(scenario['required'])
            missing_required = set(required_list[:-1])  # All but last
            result = grade_triage(
                scenario['id'],
                scenario['decision'],
                missing_required
            )
            self.assertFalse(result['passed'],
                           f"Scenario {scenario['id']}: missing required fact should fail")

    def test_selecting_wrong_fact_fails(self):
        """Selecting a wrong fact = fail."""
        for scenario in SCENARIOS:
            if not scenario['wrong']:
                # Skip scenarios with no wrong facts
                continue
            selected = scenario['required'] | {list(scenario['wrong'])[0]}
            result = grade_triage(
                scenario['id'],
                scenario['decision'],
                selected
            )
            self.assertFalse(result['passed'],
                           f"Scenario {scenario['id']}: selecting wrong fact should fail")

    def test_unknown_scenario_id_raises_keyerror(self):
        """Unknown scenario id raises KeyError."""
        with self.assertRaises(KeyError):
            grade_triage('z', 'stop', set())

    def test_result_has_required_fields(self):
        """Result dict has 'passed', 'items', 'explanation'."""
        result = grade_triage(SCENARIOS[0]['id'], SCENARIOS[0]['decision'], SCENARIOS[0]['required'])
        self.assertIn('passed', result)
        self.assertIn('items', result)
        self.assertIn('explanation', result)

    def test_items_have_required_fields(self):
        """Each item in result['items'] has '項目', '結果', '說明'."""
        result = grade_triage(SCENARIOS[0]['id'], SCENARIOS[0]['decision'], SCENARIOS[0]['required'])
        for item in result['items']:
            self.assertIn('項目', item)
            self.assertIn('結果', item)
            self.assertIn('說明', item)
            self.assertIn(item['結果'], {'✓', '✗'})

    def test_pass_result_has_passing_items(self):
        """Passing result has at least one '✓' and no '✗'."""
        result = grade_triage(SCENARIOS[0]['id'], SCENARIOS[0]['decision'], SCENARIOS[0]['required'])
        check_results = [item['結果'] for item in result['items']]
        self.assertTrue(any(r == '✓' for r in check_results))
        self.assertFalse(any(r == '✗' for r in check_results))

    def test_fail_result_has_failing_items(self):
        """Failing result has at least one '✗'."""
        scenario = SCENARIOS[0]
        wrong_decision = 'continue' if scenario['decision'] == 'stop' else 'stop'
        result = grade_triage(scenario['id'], wrong_decision, scenario['required'])
        check_results = [item['結果'] for item in result['items']]
        self.assertTrue(any(r == '✗' for r in check_results))


if __name__ == '__main__':
    unittest.main()
