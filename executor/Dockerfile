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

FROM golang:${GO_VERSION} AS build-upm

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
    python3-absl \
    python3-audioread \
    python3-contourpy \
    python3-filelock \
    python3-gensim \
    python3-h5py \
    python3-imageio \
    python3-joblib \
    python3-lazy-loader \
    python3-llvmlite \
    python3-markdown-it \
    python3-matplotlib \
    python3-mdurl \
    python3-networkx \
    python3-nltk \
    python3-numpy \
    python3-opencv \
    python3-openpyxl \
    python3-pandas \
    python3-pillow \
    python3-pip \
    python3-plotly \
    python3-pooch \
    python3-pyaudio \
    python3-pypdf2 \
    python3-pytest \
    python3-python-docx \
    python3-rich \
    python3-scipy \
    python3-seaborn \
    python3-sklearn \
    python3-soundfile \
    python3-tifffile \
    python3-tz \
    python3-venv \
    python3-xarray \
    python3-xgboost \
    python3-xlrd \
    python3-xyzservices

COPY requirements.txt /

RUN --mount=target=/root/.cache/pip,type=cache,sharing=locked \
    python3 -m venv --system-site-packages /venv && /venv/bin/pip install -r /requirements.txt

COPY execute /

COPY --from=build-upm /go/bin/upm /usr/local/bin/upm
COPY --from=build-upm /workdir/upm/internal/backends/python/pypi_map.sqlite /pypi_map.sqlite
ENV PYPI_MAP_DB=/pypi_map.sqlite

RUN mkdir /workspace && chown -R ubuntu /workspace

WORKDIR /workspace

USER ubuntu

ENV PATH="/venv/bin:$PATH"

ENTRYPOINT [ "/execute" ]
