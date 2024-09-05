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

ARG GO_VERSION="1.22.5"
ARG UPM_VERSION="2.3.0"

FROM docker.io/golang:${GO_VERSION} AS build-upm

ARG UPM_VERSION

WORKDIR /workdir

RUN git clone --depth 1 --branch "v${UPM_VERSION}" https://github.com/replit/upm.git  && \
    cd ./upm && \
    make install

FROM ubuntu:24.04 AS runtime

RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt update \
    && apt install -y --no-install-recommends \
    python3 \
    python3-matplotlib \
    python3-numpy \
    python3-pandas \
    python3-pillow \
    python3-pip \
    python3-plotly \
    python3-scipy \
    python3-sklearn \
    python3-venv

COPY requirements.txt /

RUN --mount=target=/root/.cache/pip,type=cache,sharing=locked \
    python3 -m venv --system-site-packages /venv && /venv/bin/pip install -r /requirements.txt

COPY execute /

COPY --from=build-upm /go/bin/upm /usr/local/bin/upm
COPY --from=build-upm /workdir/upm/internal/backends/python/pypi_map.sqlite /pypi_map.sqlite
ENV PYPI_MAP_DB=/pypi_map.sqlite

RUN mkdir /workspace && chmod 777 /workspace

WORKDIR /workspace

# Use an arbitrary UID
USER 1001050000

ENV PATH="/venv/bin:$PATH"

ENTRYPOINT [ "/execute" ]
