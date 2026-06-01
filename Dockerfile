# syntax=docker/dockerfile:1
# Thin Pythinker Code image: installs the published wheel from PyPI so the
# container ships the exact same artifact users get from `pip install`. No
# source build, no new Python runtime deps. The version is pinned at build time
# by docker.yml after the wheel is confirmed live on PyPI.
FROM python:3.14-slim

# Build-time pin. docker.yml passes --build-arg PYTHINKER_VERSION=<X.Y.Z>.
ARG PYTHINKER_VERSION
RUN test -n "$PYTHINKER_VERSION" || (echo "PYTHINKER_VERSION build-arg is required" >&2; exit 1)

# ripgrep is the external binary the agent shells out to; git/ca-certificates
# keep common repository and HTTPS workflows usable inside the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ripgrep git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Some already-published wheels on this release line include immutable
# dependency metadata that the current source tree has since corrected. The
# image still needs to rebuild those promoted releases from PyPI, so use pip's
# legacy resolver and keep protobuf under opentelemetry-proto's declared bound.
RUN printf 'protobuf<7\n' >/tmp/constraints.txt \
    && pip install --no-cache-dir --root-user-action=ignore \
        --constraint /tmp/constraints.txt \
        --only-binary=:all: \
        --use-deprecated=legacy-resolver \
        "pythinker-code==${PYTHINKER_VERSION}" \
    && rm /tmp/constraints.txt

# Channel marker: the in-app updater reads this and prints a docker-native hint
# instead of trying to pip-upgrade inside an immutable image.
ENV PYTHINKER_MANAGED=docker
ENV HOME=/home/pythinker

RUN useradd --create-home --shell /usr/sbin/nologin pythinker
USER pythinker

ENTRYPOINT ["pythinker"]
CMD ["--help"]
