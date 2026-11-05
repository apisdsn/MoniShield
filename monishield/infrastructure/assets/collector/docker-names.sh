#!/bin/sh
# MoniShield: name-based links to the log files of Docker containers.
#
# Docker names its log files by container id. For every container (also stopped ones, so their last lines are still read) this
# keeps   <dir>/<container name>.log -> <root>/<id>/<id>-json.log   so the collector can name the service after the container.
# Links of containers that are gone are removed, a link whose target changed (a container created again under the same name)
# is replaced. A name is cleaned to letters, digits, dot, underscore and hyphen; when two names are the same after cleaning, the
# newer container gets "-<first 8 characters of its id>". A container without a json-file log gets no link.
# When Docker cannot be asked, nothing is changed and the exit code is 1.
#
#   docker-names.sh [--dry-run] [--dir DIR] [--root DIR]
#   --dry-run  print the planned changes and change nothing
#   --dir      where the links go (default /var/lib/otelcol-contrib/containers)
#   --root     Docker's container folder (default /var/lib/docker/containers)
set -eu
LC_ALL=C; export LC_ALL   # one byte per character, so a name is cleaned the same way everywhere

DIR=/var/lib/otelcol-contrib/containers
ROOT=/var/lib/docker/containers
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --dir) [ $# -ge 2 ] || { echo 'docker-names: --dir needs a value' >&2; exit 2; }; DIR="$2"; shift 2 ;;
    --root) [ $# -ge 2 ] || { echo 'docker-names: --root needs a value' >&2; exit 2; }; ROOT="$2"; shift 2 ;;
    *) echo "docker-names: unknown option: $1" >&2; exit 2 ;;
  esac
done

LIST="$(docker ps -a --no-trunc --format '{{.ID}} {{.Names}}')" || { echo 'docker-names: cannot list the containers; links left as they are' >&2; exit 1; }

# "<link name>TAB<target>" for every container, oldest first (docker ps lists the newest first), so the oldest keeps a plain name
PLAN="$(printf '%s\n' "$LIST" | awk -v root="$ROOT" '
  NF >= 2 && $1 ~ /^[0-9a-f]+$/ { n++; id[n] = $1; nm[n] = substr($0, length($1) + 2) }
  END {
    for (i = n; i >= 1; i--) {
      name = nm[i]; sub(/,.*/, "", name); gsub(/[^A-Za-z0-9._-]/, "-", name); sub(/^[^A-Za-z0-9]+/, "", name)
      name = substr(name, 1, 200)
      if (name == "") name = substr(id[i], 1, 12)
      if (name in used) name = name "-" substr(id[i], 1, 8)
      while (name in used) name = name "_"
      used[name] = 1
      printf "%s.log\t%s/%s/%s-json.log\n", name, root, id[i], id[i]
    }
  }')"

TAB="$(printf '\t')"
WANT=''
[ "$DRY" = 1 ] || mkdir -p "$DIR"
while IFS="$TAB" read -r link target; do
  [ -n "$link" ] || continue
  [ -e "$target" ] || continue                       # another log driver: there is no file to read
  WANT="${WANT}${link}
"
  have=''
  [ -L "$DIR/$link" ] && have="$(readlink "$DIR/$link")"
  [ "$have" = "$target" ] && continue
  if [ -n "$have" ]; then act=update; else act=create; fi
  if [ "$DRY" = 1 ]; then echo "$act $link -> $target"; continue; fi
  ln -s "$target" "$DIR/.tmp-$link.new"
  mv -f "$DIR/.tmp-$link.new" "$DIR/$link"
  echo "$act $link -> $target"
done <<EOT
$PLAN
EOT

for f in "$DIR"/*.log; do
  [ -L "$f" ] || continue
  name="${f##*/}"
  if printf '%s' "$WANT" | grep -Fxq -- "$name"; then continue; fi
  echo "remove $name"
  [ "$DRY" = 1 ] || rm -f "$f"
done
exit 0
