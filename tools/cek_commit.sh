#!/bin/sh
# Conventional Commits format checker (https://www.conventionalcommits.org/id/v1.0.0/).
#   tools/cek_commit.sh --file .git/COMMIT_EDITMSG     one message (used by the .githooks/commit-msg hook)
#   tools/cek_commit.sh A..B                           every commit in the range (used by CI)
# First line: <type>[(<scope>)][!]: <summary>, max. 100 characters. git's default merge/revert commits are skipped.
TYPES='feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert'
RE="^($TYPES)(\([a-z0-9][a-z0-9._/-]*\))?!?: [^ ].{0,98}$"
cek() {
  first=$(printf '%s\n' "$1" | sed -n '1p')
  case "$first" in Merge\ *|Revert\ \"*|fixup!\ *|squash!\ *) return 0 ;; esac
  if printf '%s\n' "$first" | grep -Eq "$RE"; then return 0; fi
  echo "✗ not Conventional Commits: \"$first\"" >&2
  echo "  examples: feat(map): flow animation towards the server | fix(kafka): ... | docs: ... | chore(deps): ..." >&2
  echo "  types: ${TYPES}; optional lowercase scope; '!' for breaking changes" >&2
  return 1
}
if [ "$1" = "--file" ]; then cek "$(grep -v '^#' "$2")"; exit $?; fi
rc=0
for c in $(git rev-list --no-merges "$1"); do cek "$(git log -1 --format=%B "$c")" || { echo "  commit $c" >&2; rc=1; }; done
exit $rc
