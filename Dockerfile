ARG PYTHON_VERSION="3.12"

FROM docker.io/python:${PYTHON_VERSION}-slim AS builder
RUN apt-get update &&\
    apt-get install --no-install-suggests --no-install-recommends --yes build-essential &&\
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
WORKDIR /src
COPY . .
RUN uv sync --no-cache --link-mode copy

FROM docker.io/python:${PYTHON_VERSION}-slim AS runtime
RUN apt-get update &&\
    apt-get install --no-install-suggests --no-install-recommends --yes kubernetes-client &&\
    apt-get clean &&\
    rm -rf /var/lib/apt/lists/*
COPY --from=builder /src /src
RUN mkdir /storage && chmod 777 /storage
ENTRYPOINT ["/src/.venv/bin/python", "-m", "code_interpreter"]
