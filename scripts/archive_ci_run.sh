#!/usr/bin/env bash
# Archive one CI benchmark run to the run-records release (ADR-0017).
#
#   scripts/archive_ci_run.sh GITHUB_RUN RUN_ID
#
# GITHUB_RUN is the number at the end of the run's Actions URL, for example
# 36937530157 in .../actions/runs/36937530157 (not the short "#12" shown in
# the run list). RUN_ID is the run ID the benchmark was dispatched with,
# for example ci-w3-cache-1.
#
#   scripts/archive_ci_run.sh 36937530157 ci-w3-cache-1
#
# Downloads the run's artifacts named RUN_ID-TASK, one folder per task,
# re-validates every record, packs them as RUN_ID.tar.gz and uploads that to
# the run-records release, creating the release if needed. benchmark.yml's
# summary job runs this same script on its own run, so backfilled and new
# archives are built the same way.
#
# Never overwrites: an existing RUN_ID.tar.gz makes the upload fail, because
# records are never changed once written (ADR-0011).
#
# Needs gh (logged in, with write access to the repository) and a Python that
# has blindspots installed; set PYTHON to choose it, for example
#   PYTHON=~/.venvs/blindspots/bin/python scripts/archive_ci_run.sh 36937530157 ci-w3-cache-1

set -euo pipefail

RELEASE=run-records
PYTHON=${PYTHON:-python}

if [ "$#" -ne 2 ]; then
    sed -n '4,11p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
fi
GITHUB_RUN=$1
RUN_ID=$2

# The same rule as benchmark.yml's run-ID check: GitHub renames asset files
# with other characters, and a renamed archive would escape the exact-name
# check that refuses reused run IDs.
if ! [[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]]; then
    echo "refused: run ID '$RUN_ID' may contain only letters, digits and hyphens" >&2
    exit 1
fi
if ! [[ "$GITHUB_RUN" =~ ^[0-9]+$ ]]; then
    echo "refused: GITHUB_RUN must be the number from the run's Actions URL" >&2
    exit 1
fi

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"   # gh finds the repository from here
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
stage="$work/stage/$RUN_ID"

echo "downloading artifacts $RUN_ID-* from run $GITHUB_RUN"
gh run download "$GITHUB_RUN" --pattern "$RUN_ID-*" --dir "$stage"

# The pattern is a prefix match, so "ci-gold-*" would also take ci-gold-1's
# artifacts. Keep only exact RUN_ID-TASK names for dev-split tasks; anything
# else means the wrong run ID was given.
"$PYTHON" - "$stage" "$RUN_ID" "$repo_root/splits/dev_split.json" <<'EOF'
import json, sys
from pathlib import Path
stage, run_id, split = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
tasks = json.load(open(split))["instance_ids"]
expected = {f"{run_id}-{t}" for t in tasks}
found = sorted(p.name for p in stage.iterdir())
stray = [n for n in found if n not in expected]
if not found or stray:
    sys.exit(f"refused: artifacts {stray or found} are not {run_id}-TASK for dev-split "
             f"tasks; is {run_id} the run ID this run was dispatched with?")
print(f"{len(found)} task artifacts: {', '.join(found)}")
EOF

# Re-validate every record before it is archived for good. The records sit
# at TASK-FOLDER/records/RUN_ID/TASK.json; copied together so one summary
# covers them (summarise reads every .json under the folder it is given, so
# it must not be pointed at the harness logs).
mkdir "$work/check"
shopt -s nullglob
records=("$stage"/*/records/"$RUN_ID"/*.json)
if [ "${#records[@]}" -eq 0 ]; then
    echo "refused: no records for $RUN_ID in the downloaded artifacts" >&2
    exit 1
fi
cp "${records[@]}" "$work/check/"
"$PYTHON" -m blindspots.summarise "$work/check"

tarball="$work/$RUN_ID.tar.gz"
tar --sort=name -czf "$tarball" -C "$work/stage" "$RUN_ID"
echo "packed $(du -h "$tarball" | cut -f1) into $RUN_ID.tar.gz"

if ! gh release view "$RELEASE" >/dev/null 2>&1; then
    echo "creating release $RELEASE"
    gh release create "$RELEASE" --latest=false --title "Run records" \
        --notes "One RUN_ID.tar.gz per CI benchmark run: records, harness logs, predictions and package versions, one folder per task. Never overwritten (ADR-0011, ADR-0017)."
fi

# No --clobber: if RUN_ID.tar.gz is already there, this fails, and the
# archived copy stays as it was.
gh release upload "$RELEASE" "$tarball"

# Check the asset kept its exact name (GitHub may rename files).
release_id=$(gh api "repos/{owner}/{repo}/releases/tags/$RELEASE" --jq .id)
if ! gh api --paginate "repos/{owner}/{repo}/releases/$release_id/assets?per_page=100" \
        --jq '.[].name' | grep -qxF "$RUN_ID.tar.gz"; then
    echo "error: uploaded, but no asset is named exactly $RUN_ID.tar.gz" >&2
    exit 1
fi
echo "archived: release $RELEASE, asset $RUN_ID.tar.gz"
