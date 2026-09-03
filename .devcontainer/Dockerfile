FROM mcr.microsoft.com/devcontainers/python:3.14

# uv, from Astral's official image. The interpreter itself comes from uv, driven by
# .python-version and requires-python, not from the base image's python.
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /usr/local/bin/

# The workspace is a bind mount and uv's cache is not, so hardlinking is impossible.
ENV UV_LINK_MODE=copy

# Install dependencies needed by Home Assistant or its dependencies
RUN \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive \
        apt-get install -y --no-install-recommends \
            build-essential \
            clang \
            cmake \
            ffmpeg \
            gcc \
            git \
            libavcodec-dev \
            libavdevice-dev \
            libavfilter-dev \
            libavformat-dev \
            libavutil-dev \
            libffi-dev \
            liblzma-dev \
            libpcap-dev \
            libssl-dev \
            libswresample-dev \
            libswscale-dev \
            libturbojpeg0 \
            libudev-dev \
            libxml2 \
            libxmlsec1-dev \
            libyaml-dev \
            uuid-dev \
            webp \
            xz-utils \
            zlib1g-dev \
            vim
