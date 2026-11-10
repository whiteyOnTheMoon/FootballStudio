"""Offline tests for GitHub metadata bootstrap. No API calls or tokens needed."""
from __future__ import annotations

import importlib.util
import pathlib
import unittest
from unittest.mock import call, patch


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_roadmap.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_roadmap", SCRIPT)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapRoadmapTest(unittest.TestCase):
    def test_markdown_fields(self):
        body = ("- **Priorität:** P0 · **Typ:** docs · **Bereich:** ops\n"
                "- **Status:** Backlog")
        self.assertEqual(bootstrap.get_field(body, "Priorität"), "P0")
        self.assertEqual(bootstrap.get_field(body, "Typ"), "docs")
        self.assertEqual(bootstrap.get_field(body, "Bereich"), "ops")
        self.assertIsNone(bootstrap.get_field(body, "Unbekannt"))

    def test_rejects_wrong_repository_without_api_access(self):
        with patch.object(bootstrap, "REPO", "someone/elsewhere"), \
             patch.object(bootstrap, "TOKEN", "fake"), \
             patch.object(bootstrap, "api") as api:
            with self.assertRaises(SystemExit):
                bootstrap.main()
            api.assert_not_called()

    def test_issue_assignment_preserves_project_scope_and_existing_labels(self):
        issues = [
            {
                "number": 8, "title": "M0 / FS-004a · LLM-Kosten",
                "body": "- **Priorität:** P0\n- **Typ:** research\n- **Bereich:** backend",
                "state": "open", "milestone": None, "labels": [{"name": "custom:retain"}],
            },
            {
                "number": 15, "title": "M1 / FS-007a · Django",
                "body": "- **Priorität:** P1\n- **Typ:** feature\n- **Bereich:** web",
                "state": "closed", "milestone": {"number": 2},
                "labels": [{"name": "status:Backlog"}],
            },
            {"number": 91, "title": "docs(M0): a pull request", "pull_request": {}, "state": "open"},
        ]
        with patch.object(bootstrap, "all_pages", return_value=issues), \
             patch.object(bootstrap, "api") as api:
            bootstrap.organize_issues("/repos/a/b", {"M0": 1, "M1": 2})
            api.assert_any_call("PATCH", "/repos/a/b/issues/8", {"milestone": 1})
            api.assert_any_call("POST", "/repos/a/b/issues/8/labels",
                                {"labels": ["area:backend", "priority:P0", "status:Backlog",
                                            "type:research"]})
            api.assert_any_call("DELETE", "/repos/a/b/issues/15/labels/status%3ABacklog")
            api.assert_any_call("POST", "/repos/a/b/issues/15/labels",
                                {"labels": ["area:web", "priority:P1", "status:Done",
                                            "type:feature"]})
            self.assertFalse(any("issues/91" in str(entry) for entry in api.call_args_list))

    def test_existing_milestones_are_not_recreated(self):
        known = [{"title": name, "number": i + 1}
                 for i, name in enumerate(bootstrap.MILESTONES)]
        with patch.object(bootstrap, "all_pages", return_value=known), \
             patch.object(bootstrap, "api") as api:
            numbers = bootstrap.ensure_milestones("/repos/a/b")
            self.assertEqual(numbers["M0"], 1)
            self.assertEqual(numbers["M6"], 7)
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
