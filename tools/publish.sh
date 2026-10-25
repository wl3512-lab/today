#!/bin/bash
# Publish this checkout to the public repo as one new commit on the `public` branch.
# The public history never contains this repo's own commits (early ones held personal files):
# each release is a commit whose only parent is the previous release.
#   tools/publish.sh --dry-run    run every check, build nothing
#   tools/publish.sh --yes        check, build the release commit, push it as main and tag it
# Set the remote once:  git remote add github https://github.com/wl3512-lab/today.git
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
case "${1:-}" in --yes) DRY=0 ;; --dry-run) DRY=1 ;; *) echo "usage: $0 --dry-run | --yes"; exit 2 ;; esac
fail() { echo "STOP: $*"; exit 1; }
PY="${PYTHON:-python3}"
[ -x planner/.venv/bin/python ] && PY=planner/.venv/bin/python
VERSION=$(cat VERSION)

echo "1/5 nothing uncommitted"
[ -z "$(git status --porcelain)" ] || fail "commit or stash first:
$(git status --short)"

echo "2/5 tests"
"$PY" planner/tests/run.py >/dev/null 2>&1 || fail "planner tests fail: $PY planner/tests/run.py"
for t in planner/tests/*.test.js planner/tests/*.test.cjs quiz-prep/tests/*.test.js; do
  [ -f "$t" ] || continue
  node "$t" >/dev/null 2>&1 || fail "$t fails"
done

echo "3/5 privacy scan"
"$PY" tools/privacy_scan.py || fail "personal data found (above)"

echo "4/5 release commit for $VERSION"
git tag -l "v$VERSION" | grep -q . && fail "v$VERSION exists already: bump VERSION and add a CHANGELOG entry"
grep -q "^## $VERSION" CHANGELOG.md || fail "CHANGELOG.md has no '## $VERSION' entry"
TREE=$(git rev-parse "HEAD^{tree}")
PARENT=$(git rev-parse -q --verify refs/heads/public)
if [ "$DRY" = 1 ]; then
  echo "  would commit tree $TREE${PARENT:+ on top of public $PARENT} as v$VERSION"
  echo "  would push public -> github main, and tag v$VERSION"
  exit 0
fi
COMMIT=$(git commit-tree "$TREE" ${PARENT:+-p "$PARENT"} -m "Release $VERSION")
git update-ref refs/heads/public "$COMMIT" ${PARENT:+"$PARENT"}
git tag "v$VERSION" "$COMMIT"

echo "5/5 push"
git remote get-url github >/dev/null 2>&1 || fail "no 'github' remote (see the top of this file)"
git push github "public:refs/heads/main" "refs/tags/v$VERSION" || fail "push failed"
echo "published v$VERSION"
