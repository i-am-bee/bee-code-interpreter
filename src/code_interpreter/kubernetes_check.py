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

import asyncio
import random
from code_interpreter.services.kubectl import Kubectl
from code_interpreter.config import Config


async def kubernetes_check_async():
    config = Config()
    kubectl = Kubectl(
        context=config.kubernetes_context, namespace=config.kubernetes_namespace
    )
    pod_name = "test-" + str(random.randint(1000, 9999))

    print("ℹ️  Checking kubectl binary")
    try:
        await kubectl.config("current-context")
    except RuntimeError as e:
        print(f"Error: {e}")
        print("")
        print(
            "❌ Unable to run kubectl. Possible reasons: kubectl is not installed, kubectl is not configured to work with a cluster"
        )
        exit(1)

    print("ℹ️  Creating a pod")
    try:
        await kubectl.create(
            filename="-",
            input={
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": pod_name},
                "spec": {
                    "containers": [
                        {
                            "name": "executor",
                            "image": config.executor_image,
                            "command": ["sleep", "infinity"],
                            "resources": config.executor_container_resources,
                        }
                    ]
                },
            },
        )
    except RuntimeError as e:
        print(f"Error: {e}")
        print("")
        print(
            "❌ Unable to create a pod in the cluster. Possible reason: insufficient permissions"
        )
        exit(1)

    print("ℹ️  Getting the pod status")
    try:
        await kubectl.get("pod", pod_name)
    except RuntimeError as e:
        print(f"Error: {e}")
        print("")
        print(
            "❌ Unable to get the pod status. Possible reason: insufficient permissions"
        )
        exit(1)

    print("ℹ️  Waiting for the pod to become ready")
    try:
        await kubectl.wait("pod", pod_name, timeout="30s", _for="condition=Ready")
        print("✅ Pod is ready")
    except RuntimeError as e:
        print(f"Error: {e}")
        print("")
        print(
            "❌ Pod did not become ready. Possible reason: the pod wasn't able to pull the executor image "
        )
        exit(1)

    print("ℹ️  Executing a simple command in the pod")
    try:
        await kubectl.exec(pod_name, "--", "/execute", "print('Hello, World!')")
        print("✅ Command executed successfully")
    except RuntimeError as e:
        print(f"Error: {e}")
        print("")
        print(
            "❌ Unable to execute a command in the pod. Possible reason: insufficient permissions"
        )
        exit(1)

    print("ℹ️  Deleting the pod")
    try:
        await kubectl.delete("pod", pod_name, now=True)
    except RuntimeError as e:
        print(f"Error: {e}")
        print("")
        print("❌ Unable to delete the pod. Possible reason: insufficient permissions")
        exit(1)

    print("✅ The configured cluster is ready to use!")


def kubernetes_check():
    asyncio.run(kubernetes_check_async())


if __name__ == "__main__":
    kubernetes_check()
