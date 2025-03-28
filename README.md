<h1 align="left">BeeAI Code Interpreter</h1>

<p align="left">
  <a aria-label="Join the community on GitHub" href="https://github.com/i-am-bee/bee-code-interpreter/discussions">
    <img alt="" src="https://img.shields.io/badge/Join%20the%20community-blueviolet.svg?style=for-the-badge&labelColor=000000&label=BeeAI">
  </a>
</p>

<p align="left">
BeeAI Code Interpreter is a powerful HTTP service built to enable LLMs to execute arbitrary Python code. Engineered with safety and reproducibility at the core, this service is designed to seamlessly integrate with your applications.
</p>

> [!NOTE]
> This project includes submodules. Clone it using:
> `git clone --recurse-submodules`.
> 
> If you've already cloned it, initialize submodules with:
> `git submodule update --init`.

You can quickly set up BeeAI Code Interpreter locally without needing to install Python or Poetry, as everything runs inside Docker.

---

## ⚡ Quick start

### 👉 **Recommended: [BeeAI Framework Python Starter](https://github.com/i-am-bee/beeai-framework-py-starter)**

BeeAI Framework Python Starter helps you set up everything, including BeeAI Code Interpreter. The starter template is also available in [TypeScript](https://github.com/i-am-bee/beeai-framework-ts-starter).

## Installation

If you wish to make modifications to BeeAI Code Interpreter (like modifying the executor image), continue with the following:

1. **Install Rancher Desktop:** Download and install [Rancher Desktop](https://rancherdesktop.io/), a local Docker and Kubernetes distribution.
> [!WARNING]
> If you use a different local Docker / Kubernetes environment than Rancher Desktop, you may have a harder time.
> Most of the other options (like Podman Desktop) require an additional step to make locally built images available in Kubernetes.
> In that case, you might want to check `scripts/run-pull.sh` and modify it accordingly.

2. **Verify kubectl Context:** If you're using `kubectl` to manage Kubernetes clusters, make sure the correct context is context.

3. **Run BeeAI Code Interpreter:** Run one of the following commands to spin up BeeAI Code Interpreter in the active `kubectl` context:
    - **Use a pre-built image** (recommended if you made no changes): `bash scripts/run-pull.sh`
    - **Build image locally**: `bash scripts/run-build.sh`
> [!WARNING]
> Building the image locally make take a long time -- up to a few hours on slower machines.

4. **Interacting with the Service:** Once the service is running, you can interact with it using the HTTP API described below.

---

## 📡 HTTP API Reference

The service exposes the following HTTP endpoints:

### Execute Code

This endpoint executes arbitrary Python code in a sandboxed environment, with on-the-fly installation of any missing libraries.

> [!NOTE]
> All `import`s are checked and missing libraries are installed on-the-fly. 
> 
> `file_hash` refers to the hash-based filename as used in the storage folder.

**Endpoint:** `POST /v1/execute`

**Request Body:**
```json
{
    "source_code": string,
    "files": {
        "file_path": "file_hash"
    },
    "env": {
        "ENV_VAR": "value"
    }
}
```

**Response:**
```json
{
    "stdout": string,
    "stderr": string,
    "exit_code": number,
    "files": {
        "file_path": "file_hash"
    }
}
```

### Parse Custom Tool

This endpoint parses a custom tool definition and returns its metadata.

**Endpoint:** `POST /v1/parse-custom-tool`

**Request Body:**
```json
{
    "tool_source_code": string
}
```

**Response:**
```json
{
    "tool_name": string,
    "tool_input_schema_json": string,
    "tool_description": string
}
```

### Execute Custom Tool

This endpoint executes a custom tool with the provided input.

**Endpoint:** `POST /v1/execute-custom-tool`

**Request Body:**
```json
{
    "tool_source_code": string,
    "tool_input_json": string, // a string-encoded JSON object
    "env": {
        "ENV_VAR": "value"
    }
}
```

**Response:**
```json
{
    "tool_output_json": string
}
```

**Error Response:**
```json
{
    "stderr": string
}
```

Example using curl:
```bash
# Execute a simple Python script
curl -X POST http://localhost:50081/v1/execute \
  -H "Content-Type: application/json" \
  -d '{"source_code":"print(\"hello world\")"}'
```

---

## 🧳 Production setup

To configure BeeAI Code Interpreter for production:

1. All configuration options are located in `src/code_interpreter/config.py`. Override them using environment variables with `APP_` prefix, e.g. `APP_EXECUTOR_IMAGE` to override `executor_image`.

2. For production deployment, ensure the following:
- A Kubernetes cluster with a secure container runtime (gVisor, Kata Containers, Firecracker, etc.)
  > ⚠️ Docker containers are not fully sandboxed by default. To protect from malicious attackers, do not skip this step.
- A service account, bound to the pod where `bee-code-interpreter` is running, with permissions to manage pods in the namespace it is configured to use.
- The cluster must have the executor image available (either from a registry, or built from `./executor` in this repo).
- You may check the health of the local service using `python -m code_interpreter.health_check`.
- The shared folder with file objects should be periodically cleaned of old objects. The objects are identified by random ids and may be removed as soon as the consumer is done downloading them. If the objects are shared through a S3 bucket, we recommend setting up an auto-deletion policy.

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
VERSION=...
git checkout main
git pull
poetry version $VERSION
git add pyproject.toml
git commit -m "chore: bump version to v$VERSION"
git tag v$VERSION
git push origin main v$VERSION
```

---

## Bugs

We are using [GitHub Issues](https://github.com/i-am-bee/bee-code-interpreter/issues) to manage our public bugs. We keep a close eye on this so before filing a new issue, try to make sure the problem in not already reported.

## Code of conduct

This project and everyone participating in it are governed by the [Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please read the [full text](./CODE_OF_CONDUCT.md) so that you can read which actions may or may not be tolerated.

## Legal notice

All content in these repositories including code has been provided by IBM under the associated open source software license and IBM is under no obligation to provide enhancements, updates, or support. IBM developers produced this code as an open source project (not as an IBM product), and IBM makes no assertions as to the level of quality nor security, and will not be maintaining this code going forward.
