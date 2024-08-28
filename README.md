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

---

## 🪑 Local set-up

Pre-requisites:
- `git`
- `docker` (we recommend using [Rancher Desktop](https://rancherdesktop.io/))
- `grpcurl` (optional -- for testing)
- `python` 3.12+

### Clone this repo

This project contains submodules. Be sure to clone it with `git clone --recurse-submodules`, or initialize the submodules later with `git submodule update --init`.

### Prepare environment

```shell
python -m venv .venv
source .venv/bin/activate  # On Windows, use .venv\Scripts\activate
```

### Install dependencies

```shell
poetry install
```

### 🚀 Run

Run the server using:

```bash
poe compose-up
```

🎉 Bee Code Interpreter should now be running in the background! You can test it using `grpcurl`:

```bash
grpcurl -d '{"executor_id":"1","source_code":"print(\"hello world\")"}' -plaintext -max-time 60 127.0.0.1:50051 code_interpreter.v1.CodeInterpreterService/Execute
```

Stop the server using:

```bash
poe compose-down
```

---

## 📣 Publishing

```shell
poe publish $NEW_VERSION
```

## 🧳 Production set-up

All configuration options are defined and described in `src/code_interpreter/config.py`. You can override them using environment variables with `APP_` prefix, eg. `APP_EXECUTOR_IMAGE` to override `executor_image`.

For a production setup, ensure that you have the following:
- A Kubernetes cluster with a secure container runtime (gVisor, Kata Containers, Firecracker, etc.)
  > ⚠️ Docker containers are not fully sandboxed by default. To protect from malicious attackers, do not skip this step.
- A service account, bound to the pod where `bee-code-interpreter` is running, with permissions to manage pods in the namespace it is configured to use.
  > ℹ️ Bee Code Interpreter automatically uses a pod service account where available.
- The cluster must have the executor image available (either from a registry, or built from `./executor` in this repo).
- You may check the usability of the cluster using `python -m code_interpreter.kubernetes_check`.
- You may check the health of the local service using `python -m code_interpreter.health_check`.

## Bugs

We are using [GitHub Issues](https://github.com/i-am-bee/bee-code-interpreter/issues) to manage our public bugs. We keep a close eye on this so before filing a new issue, try to make sure the problem does not already exist.

## Code of conduct

This project and everyone participating in it are governed by the [Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please read the [full text](./CODE_OF_CONDUCT.md) so that you can read which actions may or may not be tolerated.

## Legal notice

All content in these repositories including code has been provided by IBM under the associated open source software license and IBM is under no obligation to provide enhancements, updates, or support. IBM developers produced this code as an open source project (not as an IBM product), and IBM makes no assertions as to the level of quality nor security, and will not be maintaining this code going forward.
