#!/bin/sh
set -eu

source_key=/run/reweft-key-input/permit-signing.pem
runtime_key=/run/reweft-keys/permit-signing.pem
test -f "$source_key"
install --owner reweft --group reweft --mode 0400 "$source_key" "$runtime_key"
exec runuser --user reweft -- "$@"
