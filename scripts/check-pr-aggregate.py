#!/usr/bin/env python3
"""Check that the merge gate waits for every job in `.github/workflows/pr.yml`.

`main` requires exactly one check before a pull request may merge: the aggregate job at the end of that
workflow. One name, fixed, so that adding or renaming a job is a change to the tree rather than a visit to
the repository's settings — where nothing shows up in a diff.

What the one name buys has to be paid for here. The aggregate waits for what its `needs:` names and nothing
else, so a job added without a line there is a job the required check never waits for: the run is green, the
merge goes through, and nothing anywhere says that job's verdict went uncounted. A red build cannot report
that failure, which is why it is asked of the tree instead.

Four things are checked:

1. every job in the workflow is named in the aggregate's `needs:`;
2. that list names only jobs the workflow actually has — a `needs:` pointing nowhere stops the whole run
   from loading, so it is worth catching before the push rather than after;
3. the aggregate still runs on `always()`, without which a failed dependency *skips* it instead of failing
   it, and a skipped required check is not a red one;
4. it still carries the name the branch requires, which is matched as text — renamed here alone, it becomes
   a required check nothing reports, and a merge that waits forever.

The two constants below are written out rather than read from the file, so that deleting or renaming the
gate fails this check instead of quietly leaving it with nothing to compare. If the gate really does move,
move the branch's ruleset and these two lines together.

Usage: python3 scripts/check-pr-aggregate.py   (no arguments)
Exit codes: 0 = the gate waits for every job, 1 = it drifted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The aggregate job's id, and the check name the ruleset on `main` requires — which for a job in a workflow
# of this repository's own is its `name:`, verbatim.
AGGREGATE = "all-green"
REQUIRED_CHECK = "all green"

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "pr.yml"


def read_jobs(lines: list[str]) -> tuple[list[str], list[str]]:
    """Return the workflow's job ids, and the body lines of the aggregate job.

    The job ids are the keys indented two spaces under `jobs:`, which runs to the end of the file. Anything
    deeper belongs to a job's body, and a comment may sit at any column, including the first.
    """
    jobs: list[str] = []
    aggregate: list[str] = []
    current: str | None = None
    in_jobs = False
    for line in lines:
        if not in_jobs:
            in_jobs = line.rstrip() == "jobs:"
            continue
        if re.match(r"^[A-Za-z_]", line):
            break
        key = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if key:
            current = key.group(1)
            jobs.append(current)
        elif current == AGGREGATE:
            aggregate.append(line)
    return jobs, aggregate


def read_needs(aggregate: list[str]) -> list[str]:
    """Return what the aggregate's `needs:` names, written either as a flow list or as a block list."""
    needs: list[str] = []
    collecting = False
    for line in aggregate:
        head = re.match(r"^    needs:\s*(.*)$", line)
        if head:
            rest = head.group(1).strip()
            if rest.startswith("["):
                needs += re.findall(r"[A-Za-z0-9_-]+", rest)
            else:
                collecting = True
        elif collecting:
            item = re.match(r"^      - ([A-Za-z0-9_-]+)\s*$", line)
            if item:
                needs.append(item.group(1))
            elif line.strip() and not line.lstrip().startswith("#"):
                collecting = False
    return needs


def main() -> int:
    if not WORKFLOW.is_file():
        print(f"✗ pr gate: {WORKFLOW} is missing — did the merge gate move?", file=sys.stderr)
        return 1

    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    jobs, aggregate = read_jobs(lines)

    if AGGREGATE not in jobs:
        print(
            f"✗ pr gate: pr.yml has no `{AGGREGATE}` job.\n"
            "    That job is the one check main requires, so removing it leaves the branch waiting for a "
            "verdict nothing reports. Put it back, or move the ruleset and this script with it.",
            file=sys.stderr,
        )
        return 1

    ok = True
    expected = [job for job in jobs if job != AGGREGATE]
    needs = read_needs(aggregate)

    missing = [job for job in expected if job not in needs]
    if missing:
        ok = False
        print(
            f"✗ pr gate: {', '.join(missing)} — no line in `{AGGREGATE}`'s needs.\n"
            "    The required check does not wait for them, so it goes green without their verdict. Add "
            "them to the needs list in .github/workflows/pr.yml.",
            file=sys.stderr,
        )

    stale = [need for need in needs if need not in expected]
    if stale:
        ok = False
        print(
            f"✗ pr gate: `{AGGREGATE}` needs {', '.join(stale)}, which pr.yml has no job for.\n"
            "    A run cannot even start with a needs entry pointing nowhere — the whole workflow fails to "
            "load. Drop them, or restore the jobs.",
            file=sys.stderr,
        )

    if not any(re.match(r"^    if:.*always\(\)", line) for line in aggregate):
        ok = False
        print(
            f"✗ pr gate: `{AGGREGATE}` no longer runs on `always()`.\n"
            "    Without it a failed job skips the aggregate instead of failing it, and a skipped required "
            "check is not a red one.",
            file=sys.stderr,
        )

    if not any(re.match(rf"^    name:\s*{re.escape(REQUIRED_CHECK)}\s*$", line) for line in aggregate):
        ok = False
        print(
            f"✗ pr gate: `{AGGREGATE}` is no longer named `{REQUIRED_CHECK}`.\n"
            "    That name is what main's ruleset requires, and it is matched as text — renamed here and "
            "nowhere else, the required check is one nothing reports, and every pull request waits forever.",
            file=sys.stderr,
        )

    if ok:
        print(f"✓ pr gate: `{REQUIRED_CHECK}` waits for all {len(expected)} job(s) in pr.yml")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
