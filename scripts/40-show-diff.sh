#!/usr/bin/env bash
# Show the "fix" on screen: the YAML diff between BEFORE and AFTER (good for a slide or the live demo).
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
diff -u --label before "$ROOT/manifests/10-app-before.yaml" --label after "$ROOT/manifests/20-app-after.yaml" || true
