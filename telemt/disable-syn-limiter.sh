#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <telemt.toml>" >&2
  exit 2
fi

config_path=$1
test -f "$config_path"

temporary_path=$(mktemp "${config_path}.synlimit.XXXXXX")
trimmed_path="${temporary_path}.trimmed"
trap 'rm -f "$temporary_path" "$trimmed_path"' EXIT HUP INT TERM

final_newline_count=0
if [ -s "$config_path" ]; then
  final_newline_count=$(tail -c 1 "$config_path" | wc -l | tr -d ' ')
fi

awk '
{
  line = $0
  if (line ~ /^[[:space:]]*synlimit[[:space:]]*=[[:space:]]*"(iptables|nftables)"[[:space:]]*(#.*)?$/) {
    sub(/"(iptables|nftables)"/, "false", line)
  } else if (line ~ /^[[:space:]]*synlimit[[:space:]]*=[[:space:]]*\047(iptables|nftables)\047[[:space:]]*(#.*)?$/) {
    sub(/\047(iptables|nftables)\047/, "false", line)
  }
  print line
}
' "$config_path" > "$temporary_path"

if [ "$final_newline_count" -eq 0 ] && [ -s "$temporary_path" ]; then
  temporary_size=$(wc -c < "$temporary_path" | tr -d ' ')
  dd if="$temporary_path" of="$trimmed_path" bs=1 \
    count=$((temporary_size - 1)) 2>/dev/null
  mv "$trimmed_path" "$temporary_path"
fi

if ! cmp -s "$config_path" "$temporary_path"; then
  cat "$temporary_path" > "$config_path"
fi
