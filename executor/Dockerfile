# Copyright 2024 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

ARG GO_VERSION="1.23"
ARG UPM_VERSION="2.5.2"
ARG ALPINE_VERSION="3.20"
ARG RUST_VERSION="1.81"
ARG PYTHON_VERSION="3.12"
ARG UID="1001050000"

FROM docker.io/rust:${RUST_VERSION}-alpine${ALPINE_VERSION} AS build-executor-server
WORKDIR /workdir
RUN apk add --no-cache musl-dev
COPY Cargo.toml Cargo.lock dummy.rs ./
RUN cargo build --release --bin dummy
COPY server.rs ./
RUN cargo build --release --bin executor-server

FROM docker.io/golang:${GO_VERSION}-alpine${ALPINE_VERSION} AS build-upm
ARG UPM_VERSION
WORKDIR /workdir
RUN apk add --no-cache git make gcc g++ musl-dev && \
    git clone --depth 1 --branch "v${UPM_VERSION}" https://github.com/replit/upm.git  && \
    cd ./upm && \
    export CGO_CFLAGS="-D_LARGEFILE64_SOURCE" && \
    make install

FROM docker.io/alpine:${ALPINE_VERSION} AS build-pymupdf
RUN apk add --no-cache gcc musl-dev linux-headers make g++ clang-dev python3 python3-dev py3-pip && \
    pip install --target /out pymupdf

FROM docker.io/alpine:${ALPINE_VERSION} AS runtime
RUN apk add --no-cache --repository=https://dl-cdn.alpinelinux.org/alpine/edge/testing \
    bash \
    coreutils \
    ffmpeg \
    ghostscript-fonts \
    imagemagick \
    mupdf-tools \
    opencv \
    pandoc-cli \
    python3 \
    py3-ffmpeg \
    py3-ffmpeg-pyc \
    py3-jinja2 \
    py3-jinja2-pyc \
    py3-matplotlib \
    py3-matplotlib-pyc \
    py3-moviepy \
    py3-moviepy-pyc \
    py3-numpy \
    py3-numpy-pyc \
    py3-opencv \
    py3-opencv-pyc \
    py3-pandas \
    py3-pandas-pyc \
    py3-pikepdf \
    py3-pikepdf-pyc \
    py3-pillow \
    py3-pillow-pyc \
    py3-pip \
    py3-pip-pyc \
    py3-pypandoc \
    py3-pypandoc-pyc \
    py3-scipy \
    py3-scipy-pyc \
    py3-sympy \
    py3-sympy-pyc \
    py3-tabulate \
    py3-tabulate-pyc \
    py3-xarray \
    py3-xarray-pyc \
    weasyprint \
    yt-dlp

# Create user manually -- Alpine does not support high UIDs
ARG UID
RUN echo "executor:x:${UID}:${UID}::/home/executor:" >> /etc/passwd && \
    echo "executor:!::0:::::" >> /etc/shadow && \
    echo "executor:x:${UID}:" >> /etc/group && \
    mkdir -p /home/executor /workspace /venv && \
    chown -R executor:executor /home/executor /workspace /venv
USER executor

# fontconfig
RUN fc-cache -fv

# Python
COPY requirements.txt requirements-skip.txt /
RUN python -m venv --system-site-packages /venv && /venv/bin/pip install --no-cache-dir -r /requirements.txt
COPY sitecustomize.py /venv/lib/python3.12/site-packages
ENV PATH="/venv/bin:$PATH"

# Pandoc
COPY pandoc-wrapper /usr/local/bin/pandoc

# ffmpeg
COPY ffmpeg-wrapper /usr/local/bin/ffmpeg
ENV IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg

# xonsh
ENV XONSH_SHOW_TRACEBACK=True

# UPM
COPY --from=build-upm /go/bin/upm /usr/local/bin/upm
COPY --from=build-upm /workdir/upm/internal/backends/python/pypi_map.sqlite /pypi_map.sqlite
ENV PYPI_MAP_DB=/pypi_map.sqlite

# pymupdf
ARG PYTHON_VERSION
COPY --from=build-pymupdf /out/. /venv/lib/python${PYTHON_VERSION}/site-packages/

# Executor server
COPY --from=build-executor-server /workdir/target/release/executor-server /usr/local/bin/executor-server

WORKDIR /workspace
ENTRYPOINT [ "executor-server" ]
