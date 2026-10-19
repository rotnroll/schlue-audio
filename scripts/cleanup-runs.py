"""Prune completed Actions runs; never access or modify GitHub Releases."""

import argparse
import json
import os
import subprocess


def api(path, method="GET", paginate=False):
    command = ["gh", "api", path, "--method", method]
    if paginate:
        command += ["--paginate", "--slurp"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def candidates(runs):
    """Keep newest completed per workflow/branch; freeze groups with active runs."""
    groups = {}
    for run in runs:
        if not run.get("head_branch") or not run.get("head_repository"):
            continue
        key = (run["workflow_id"], run["head_repository"]["id"], run["head_branch"])
        groups.setdefault(key, []).append(run)
    remove = []
    for group in groups.values():
        if any(run["status"] != "completed" for run in group):
            continue
        ordered = sorted(group, key=lambda run: (run["created_at"], run["id"]), reverse=True)
        remove.extend(ordered[1:])
    return sorted(remove, key=lambda run: run["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository")
    parser.add_argument("--apply", action="store_true", help="Delete; default is read-only preview")
    args = parser.parse_args()
    if not args.repository.startswith("rotnroll/") or args.repository.count("/") != 1:
        parser.error("Expected an explicitly named rotnroll repository")
    prefix = f"repos/{args.repository}/actions"
    pages = api(f"{prefix}/runs?per_page=100", paginate=True)
    runs = [run for page in pages for run in page["workflow_runs"]]
    selected = candidates(runs)
    artifact_pages = api(f"{prefix}/artifacts?per_page=100", paginate=True)
    artifacts = [item for page in artifact_pages for item in page["artifacts"] if not item["expired"]]
    ids = {run["id"] for run in selected}
    reclaimed = sum(item["size_in_bytes"] for item in artifacts if item["workflow_run"]["id"] in ids)
    retained = sum(item["size_in_bytes"] for item in artifacts) - reclaimed
    report = (f"{args.repository}: {len(selected)} old runs; "
              f"{reclaimed / 1_000_000:.1f} MB removable; {retained / 1_000_000:.1f} MB retained")
    print(report, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(report + "\n")
    for run in selected:
        print(f"{'DELETE' if args.apply else 'PREVIEW'} {run['id']} {run['name']} {run['head_branch']}", flush=True)
        if args.apply:
            # Recheck immediately before deletion in case somebody requested a rerun.
            current = api(f"{prefix}/runs/{run['id']}")
            if current["status"] != "completed" or current["run_attempt"] != run["run_attempt"]:
                raise RuntimeError(f"Run {run['id']} changed during cleanup; stopping")
            api(f"{prefix}/runs/{run['id']}", method="DELETE")


if __name__ == "__main__":
    main()
