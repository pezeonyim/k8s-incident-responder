# The devcontainer Dockerfile is built BEFORE features are installed, which is the
# only place we can repair the base image's apt sources.
#
# Why this file exists:
#   mcr.microsoft.com/devcontainers/python:1-3.12-bookworm ships an apt source for
#   dl.yarnpkg.com whose signing key is no longer trusted. Any `apt-get update` in
#   that image emits
#       W: GPG error: https://dl.yarnpkg.com/debian stable InRelease: NO_PUBKEY 62D54FD4003F6525
#   and exits 100. The Docker-in-Docker feature runs `apt-get update` during install,
#   treats the non-zero exit as fatal, and the whole container build fails -- which is
#   what dropped the Codespace into recovery mode. Nothing is wrong with the feature.
#
# The repair is to drop the unrelated yarn source (this project does not use yarn)
# and prove apt works again before the feature layer runs.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

RUN grep -rl 'yarnpkg' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null | xargs -r rm -f \
 && rm -f /usr/share/keyrings/yarn*.gpg /etc/apt/trusted.gpg.d/yarn*.gpg \
 && apt-get update \
 && rm -rf /var/lib/apt/lists/*
