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

ARG GO_VERSION="1.23.0"
ARG UPM_VERSION="2.5.0"
ARG ALPINE_VERSION="3.20"
ARG RUST_VERSION="1.81"

FROM docker.io/rust:${RUST_VERSION}-alpine${ALPINE_VERSION} AS build-executor-server
WORKDIR /workdir
RUN apk add --no-cache musl-dev
COPY --link Cargo.toml .
COPY --link Cargo.lock .
COPY --link server.rs .
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
    python3 \
    py3-matplotlib \
    py3-numpy \
    py3-pandas \
    py3-pillow \
    py3-pip \
    py3-scipy \
    py3-scikit-learn
COPY --link --from=build-executor-server /workdir/target/release/executor-server /usr/local/bin/executor-server
COPY --link --from=build-upm /go/bin/upm /usr/local/bin/upm
COPY --link --from=build-upm /workdir/upm/internal/backends/python/pypi_map.sqlite /pypi_map.sqlite
ENV PYPI_MAP_DB=/pypi_map.sqlite
RUN mkdir /workspace && chmod 777 /workspace
WORKDIR /workspace
USER 1001050000
ENTRYPOINT [ "executor-server" ]