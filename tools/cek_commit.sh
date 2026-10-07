#!/bin/sh
# Pemeriksa format Conventional Commits (https://www.conventionalcommits.org/id/v1.0.0/).
#   tools/cek_commit.sh --file .git/COMMIT_EDITMSG     satu pesan (dipakai hook .githooks/commit-msg)
#   tools/cek_commit.sh A..B                           semua commit di rentang (dipakai CI)
# Baris pertama: <tipe>[(<cakupan>)][!]: <ringkasan>, maks. 100 karakter. Commit merge/revert bawaan git dilewati.
TYPES='feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert'
RE="^($TYPES)(\([a-z0-9][a-z0-9._/-]*\))?!?: [^ ].{0,98}$"
cek() {
  first=$(printf '%s\n' "$1" | sed -n '1p')
  case "$first" in Merge\ *|Revert\ \"*|fixup!\ *|squash!\ *) return 0 ;; esac
  if printf '%s\n' "$first" | grep -Eq "$RE"; then return 0; fi
  echo "✗ bukan Conventional Commits: \"$first\"" >&2
  echo "  contoh: feat(peta): animasi alur menuju server | fix(kafka): ... | docs: ... | chore(deps): ..." >&2
  echo "  tipe: ${TYPES}; cakupan opsional huruf kecil; '!' untuk perubahan yang memutus kompatibilitas" >&2
  return 1
}
if [ "$1" = "--file" ]; then cek "$(grep -v '^#' "$2")"; exit $?; fi
rc=0
for c in $(git rev-list --no-merges "$1"); do cek "$(git log -1 --format=%B "$c")" || { echo "  commit $c" >&2; rc=1; }; done
exit $rc
