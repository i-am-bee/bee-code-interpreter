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

FROM docker.io/rust:${RUST_VERSION}-alpine${ALPINE_VERSION} AS build-executor-server
WORKDIR /workdir
RUN apk add --no-cache musl-dev
COPY Cargo.toml .
COPY Cargo.lock .
COPY server.rs .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/workdir/target/release/build \
    --mount=type=cache,target=/workdir/target/release/deps \
    cargo build --release

FROM docker.io/golang:${GO_VERSION}-alpine${ALPINE_VERSION} AS build-upm
ARG UPM_VERSION
WORKDIR /workdir
RUN apk add --no-cache git make gcc g++ musl-dev && \
    git clone --depth 1 --branch "v${UPM_VERSION}" https://github.com/replit/upm.git  && \
    cd ./upm && \
    export CGO_CFLAGS="-D_LARGEFILE64_SOURCE" && \
    make install

FROM docker.io/alpine:${ALPINE_VERSION} AS runtime
RUN apk add --no-cache \
    coreutils \
    ffmpeg \
    imagemagick \
    pandoc-cli \
    python3 \
    py3-jinja2 \
    py3-matplotlib \
    py3-matplotlib-venn \
    py3-numpy \
    py3-pandas \
    py3-pillow \
    py3-pip \
    py3-scipy \
    py3-sympy \
    py3-tabulate \
    py3-xarray \
    texlive
COPY --from=build-executor-server /workdir/target/release/executor-server /usr/local/bin/executor-server
COPY --from=build-upm /go/bin/upm /usr/local/bin/upm
COPY --from=build-upm /workdir/upm/internal/backends/python/pypi_map.sqlite /pypi_map.sqlite
ENV PYPI_MAP_DB=/pypi_map.sqlite
RUN mkdir /venv /workspace /mplconfigdir && chmod 777 /venv /workspace /mplconfigdir
ENV MPLCONFIGDIR="/mplconfigdir"
WORKDIR /workspace
USER 1001050000
RUN python -m venv --system-site-packages /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install \
    ffmpeg-python \
    pandas[excel,plot,output-formatting,computation] \
    pypandoc \
    PyPDF2 \
    python-docx \
    python-pptx
COPY sitecustomize.py /venv/lib/python3.12/site-packages
ENTRYPOINT [ "executor-server" ]