<p align="center">
    <img src="./docs/assets/Bee_Dark.svg" height="128">
    <h1 align="center">bee-code-interpreter</h1>
</p>

<p align="center">
  <a aria-label="Join the community on GitHub" href="https://github.com/i-am-bee/bee-code-interpreter/discussions">
    <img alt="" src="https://img.shields.io/badge/Join%20the%20community-blueviolet.svg?style=for-the-badge&labelColor=000000&label=Bee">
  </a>
</p>

A gRPC service intended as a backend for an LLM that can run arbitrary pieces of Python code.

Built from the ground up to be safe and reproducible.

> [!NOTE]
> This project contains submodules. Be sure to clone it with `git clone --recurse-submodules`, or initialize the submodules later with `git submodule update --init`.

---

## 🪑 Local set-up

It is possible to quickly spin up Bee Code Interpreter locally. It is not necessary to have Python or Poetry set up for this, since all is done using Docker.

The only requirement is [Rancher Desktop](https://rancherdesktop.io/) -- a local Docker and Kubernetes distribution.

> [!CAUTION]
> If you use a different local Docker / Kubernetes environment than Rancher Desktop, you may have a harder time.
> Many implementations (like Podman Desktop) require an additional step to make locally built images available in Kubernetes.
> In that case, you might want to check `scripts/run.sh` and modify it accordingly.

The following script will build the two containers (`code-interpreter` and `code-interpreter-executor`) and set up an instance of Bee Code Interpreter in your local Kubernetes cluster.

> [!CAUTION]
> Ensure that you have the correct context selected in `kubectl` before running this command.

```shell
bash ./scripts/run.sh
```

Once you see the line `INFO:root:Starting server on insecure port 0.0.0.0:50051`, Bee Code Interpreter should now be running!

In order to interact with the service, install `grpcurl`. Run "hello world" with:

```bash
grpcurl -d '{"executor_id": "test", "source_code":"print(\"hello world\")"}' -plaintext -max-time 60 127.0.0.1:50051 code_interpreter.v1.CodeInterpreterService/Execute
```

---

## 🧳 Production setup

All configuration options are defined and described in `src/code_interpreter/config.py`. You can override them using environment variables with `APP_` prefix, e.g. `APP_EXECUTOR_IMAGE` to override `executor_image`.

For a production setup, ensure that you have the following:
- A Kubernetes cluster with a secure container runtime (gVisor, Kata Containers, Firecracker, etc.)
  > ⚠️ Docker containers are not fully sandboxed by default. To protect from malicious attackers, do not skip this step.
- A service account, bound to the pod where `bee-code-interpreter` is running, with permissions to manage pods in the namespace it is configured to use.
- The cluster must have the executor image available (either from a registry, or built from `./executor` in this repo).
- You may check the health of the local service using `python -m code_interpreter.health_check`.

---

## 🧑‍💻 Development

#### Install dependencies:

Use [mise-en-place](https://mise.jdx.dev/) to install dependencies: `mise install`.

If you don't want to use `mise`, look into the file `.mise.toml` and install the listed dependencies however you see fit.

Afterwards, install the project dependencies using `poetry install`.

#### Run end-to-end tests:

``` bash
# in 1st terminal (Bee Code Interpreter must be running for end-to-end tests to work):
poe run

# in 2nd terminal:
poe test
```

#### Publish a new version:

```shell
poe publish $NEW_VERSION
```

---

## Bugs

We are using [GitHub Issues](https://github.com/i-am-bee/bee-code-interpreter/issues) to manage our public bugs. We keep a close eye on this so before filing a new issue, try to make sure the problem in not already reported.

## Code of conduct

This project and everyone participating in it are governed by the [Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please read the [full text](./CODE_OF_CONDUCT.md) so that you can read which actions may or may not be tolerated.

## Legal notice

All content in these repositories including code has been provided by IBM under the associated open source software license and IBM is under no obligation to provide enhancements, updates, or support. IBM developers produced this code as an open source project (not as an IBM product), and IBM makes no assertions as to the level of quality nor security, and will not be maintaining this code going forward.
