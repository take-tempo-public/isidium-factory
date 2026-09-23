#!/bin/sh
# The one way a runner image is made [owner, 2026-09-23]: `podman build` of `Containerfile.runner`, with the prompt
# set it copies written into the image as the `org.isidium.prompts` label. The factory reads that label before any
# spend (`Container.prompts`, `adapter.require_prompts`) and refuses an image without it, so an image built by hand
# is refused rather than trusted. The label is a second statement of what `prompts/` holds — the cost named at the
# ruling — and this script is what keeps the two the same: it reads the directory the build copies, at build time.
#
#   deploy/build-runner.sh <tag> <claude-code-version>   build, from anywhere in the repo
#   deploy/build-runner.sh --label                        print the label alone (what the suite checks)
set -eu
cd "$(dirname "$0")/.."

label() {
    (cd prompts && find . -type f -name 'v*.md' | sed 's|^\./||; s|\.md$||' | LC_ALL=C sort | paste -sd, -)
}

if [ "${1:-}" = "--label" ]; then
    label
    exit 0
fi
[ $# -eq 2 ] || { echo "usage: $0 <tag> <claude-code-version> | --label" >&2; exit 2; }
set="$(label)"
[ -n "$set" ] || { echo "build-runner: no prompts under prompts/" >&2; exit 2; }
exec podman build -f deploy/Containerfile.runner -t "$1" --build-arg "CLAUDE_CODE_VERSION=$2" \
    --label "org.isidium.prompts=$set" .
