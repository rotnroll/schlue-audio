import importlib.util
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import call, patch

spec = importlib.util.spec_from_file_location("cleanup_runs", Path(__file__).resolve().parents[1] / "scripts/cleanup-runs.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


def run(number, branch="main", workflow=1, status="completed", repository=1):
    return dict(id=number, head_branch=branch, workflow_id=workflow, status=status,
                head_repository={"id": repository}, created_at="2026-09-14T00:00:00Z",
                run_attempt=1, name="Build")


class CleanupTests(unittest.TestCase):
    def test_latest_per_branch_and_workflow(self):
        runs = [run(1), run(2), run(3, "feature"), run(4, "feature"), run(5, workflow=2)]
        self.assertEqual([r["id"] for r in cleanup.candidates(runs)], [1, 3])

    def test_active_group_keeps_its_old_packages(self):
        for status in ("queued", "in_progress", "waiting", "requested", "pending"):
            self.assertEqual(cleanup.candidates([run(1), run(2), run(3, status=status)]), [])

    def test_forks_are_not_grouped_with_source(self):
        self.assertEqual(cleanup.candidates([run(1), run(2, repository=2)]), [])

    def test_unknown_branch_is_preserved(self):
        self.assertEqual(cleanup.candidates([run(1, None), run(2, None)]), [])

    def test_creation_time_precedes_id(self):
        older = run(9)
        older["created_at"] = "2026-09-13T00:00:00Z"
        self.assertEqual([r["id"] for r in cleanup.candidates([run(1), older])], [9])

    def test_unknown_repository_is_preserved(self):
        unknown = run(1)
        unknown["head_repository"] = None
        self.assertEqual(cleanup.candidates([unknown, run(2)]), [])


class CleanupApiTests(unittest.TestCase):
    prefix = "repos/rotnroll/rerider/actions"

    def invoke(self, responses, *arguments):
        self.output = io.StringIO()
        with patch.object(cleanup, "api", side_effect=responses) as api, \
                patch("sys.argv", ["cleanup-runs.py", "rotnroll/rerider", *arguments]), \
                patch.dict(cleanup.os.environ, {"GITHUB_STEP_SUMMARY": ""}), \
                redirect_stdout(self.output):
            self.api = api
            cleanup.main()

    def listing(self, runs=None):
        return [
            [{"workflow_runs": runs if runs is not None else [run(1), run(2)]}],
            [{"artifacts": [
                {"expired": False, "size_in_bytes": 1_000_000, "workflow_run": {"id": 1}},
                {"expired": False, "size_in_bytes": 2_000_000, "workflow_run": {"id": 2}},
                {"expired": True, "size_in_bytes": 4_000_000, "workflow_run": {"id": 1}},
            ]}],
        ]

    def test_preview_only_lists_and_never_deletes(self):
        self.invoke(self.listing())
        self.assertEqual(self.api.call_args_list, [
            call(f"{self.prefix}/runs?per_page=100", paginate=True),
            call(f"{self.prefix}/artifacts?per_page=100", paginate=True),
        ])
        self.assertIn("1.0 MB removable; 2.0 MB retained", self.output.getvalue())
        self.assertIn("PREVIEW 1 Build main", self.output.getvalue())

    def test_apply_rechecks_and_deletes_only_selected_old_run(self):
        self.invoke([*self.listing(), run(1), None], "--apply")
        self.assertEqual(self.api.call_args_list[2:], [
            call(f"{self.prefix}/runs/1"),
            call(f"{self.prefix}/runs/1", method="DELETE"),
        ])
        self.assertTrue(all(c.args[0].startswith(self.prefix + "/")
                            for c in self.api.call_args_list))

    def test_rerun_or_changed_attempt_stops_before_deletion(self):
        for changes in ({"status": "in_progress"}, {"run_attempt": 2}):
            with self.subTest(changes=changes):
                current = {**run(1), **changes}
                with self.assertRaisesRegex(RuntimeError, "changed during cleanup"):
                    self.invoke([*self.listing(), current], "--apply")
                self.assertFalse(any(c.kwargs.get("method") == "DELETE"
                                     for c in self.api.call_args_list))

    def test_api_error_stops_without_deleting_another_run(self):
        error = subprocess.CalledProcessError(1, ["gh", "api"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke([*self.listing([run(1), run(2), run(3)]), run(1), error], "--apply")
        self.assertEqual(self.api.call_args_list[-1], call(f"{self.prefix}/runs/1", method="DELETE"))
        self.assertEqual(len(self.api.call_args_list), 4)

    def test_list_error_cannot_turn_into_deletion(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke([subprocess.CalledProcessError(1, ["gh", "api"])], "--apply")
        self.assertEqual(self.api.call_count, 1)

    def test_active_group_is_preserved_in_apply_mode(self):
        self.invoke(self.listing([run(1), run(2, status="in_progress")]), "--apply")
        self.assertEqual(self.api.call_count, 2)

    def test_foreign_repository_rejected_before_any_api_call(self):
        with patch.object(cleanup, "api") as api, \
                patch("sys.argv", ["cleanup-runs.py", "someone/other-repo", "--apply"]), \
                redirect_stdout(io.StringIO()), patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                cleanup.main()
            self.assertEqual(error.exception.code, 2)
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
