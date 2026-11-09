"""Planner plan-parsing: JSON extraction, alternate keys, truncation fallback."""
from services.agent.planner import TaskPlanner


class TestParsePlan:
    def test_clean_json(self):
        plan = TaskPlanner._parse_plan(
            '{"subtasks":[{"phase":"recon","title":"Recon","description":"map the surface"}]}')
        assert plan == [{"phase": "recon", "title": "Recon", "description": "map the surface"}]

    def test_json_embedded_in_prose(self):
        plan = TaskPlanner._parse_plan(
            'Here is the plan:\n{"subtasks":[{"phase":"reporting","title":"Report"}]}\nGood luck.')
        assert plan and plan[0]["phase"] == "reporting"

    def test_tasks_key_alias(self):
        plan = TaskPlanner._parse_plan('{"tasks":[{"title":"Enumerate"}]}')
        assert plan == [{"phase": "recon", "title": "Enumerate", "description": ""}]

    def test_truncated_json_returns_empty(self):
        assert TaskPlanner._parse_plan('{"subtasks":[{"phase":"recon","title":"Rec') == []

    def test_no_json_returns_empty(self):
        assert TaskPlanner._parse_plan("I could not produce a plan.") == []

    def test_entries_without_title_skipped(self):
        plan = TaskPlanner._parse_plan('{"subtasks":[{"phase":"recon"},{"title":"Real"}]}')
        assert len(plan) == 1
