FROM python:3.12 AS builder

RUN apt-get update &&\
    apt-get install --no-install-suggests --no-install-recommends --yes pipx

ENV PATH="/root/.local/bin:${PATH}"

RUN pipx install poetry &&\
    pipx inject poetry poetry-plugin-bundle

WORKDIR /src

COPY . .

RUN poetry bundle venv --python=/usr/local/bin/python --only=main /venv


FROM python:3.12-slim AS runtime

COPY --from=bitnami/kubectl:1.26.15 /opt/bitnami/kubectl/bin/kubectl /usr/local/bin/kubectl

COPY --from=builder /venv /venv

ENV PATH="/venv/bin:${PATH}"

ENTRYPOINT ["python", "-m", "code_interpreter"]

HEALTHCHECK CMD ["python", "-m", "code_interpreter.health_check"]

EXPOSE 50051
