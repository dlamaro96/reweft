#!/usr/bin/env sh
set -eu
required='README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md CONTRIBUTING.md CODE_OF_CONDUCT.md GOVERNANCE.md MAINTAINERS.md SECURITY.md SUPPORT.md contracts/acceptance.yaml'
for path in $required; do test -s "$path" || { echo "missing or empty: $path" >&2; exit 1; }; done
if git grep -nE '(BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY|AKIA[0-9A-Z]{16})' -- . ':!scripts/release-check.sh'; then
  echo "Potential committed secret material detected." >&2
  exit 1
fi
echo "Repository policy files present; no simple private-key/AWS-key pattern found. This is not a complete security audit."

