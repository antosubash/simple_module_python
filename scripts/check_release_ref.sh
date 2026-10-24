#!/usr/bin/env bash
# Check both at version selection and after builds, before publishing (#628).
set -euo pipefail

if [ "$GITHUB_REF" != "refs/heads/main" ]; then
  echo "::error::Releases must be dispatched from main"
  exit 1
fi
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
if [ "$GITHUB_SHA" != "$(git rev-parse origin/main)" ]; then
  echo "::error::Dispatch SHA is no longer origin/main; dispatch a new release from main"
  exit 1
fi
