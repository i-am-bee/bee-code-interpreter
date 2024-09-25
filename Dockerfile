ARG PYTHON_VERSION="3.12"

FROM docker.io/python:${PYTHON_VERSION} AS builder
RUN apt-get update &&\
    apt-get install --no-install-suggests --no-install-recommends --yes pipx

ENV PATH="/root/.local/bin:${PATH}"
RUN pipx install poetry &&\
    pipx inject poetry poetry-plugin-bundle
WORKDIR /src
COPY . .
RUN poetry bundle venv --python=/usr/local/bin/python --only=main /venv

FROM docker.io/python:${PYTHON_VERSION}-slim AS runtime
RUN apt-get update &&\
    apt-get install --no-install-suggests --no-install-recommends --yes kubernetes-client &&\
    apt-get clean &&\
    rm -rf /var/lib/apt/lists/*
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:${PATH}"
ENTRYPOINT ["python", "-m", "code_interpreter"]
