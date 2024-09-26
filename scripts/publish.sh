#!/bin/bash
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
set -e

REPOSITORY="docker.io"
USER="iambeeagent"
CODE_EXECUTOR_NAME="bee-code-executor"
CODE_INTERPRETER_NAME="bee-code-interpreter"
PLATFORMS="linux/amd64,linux/arm64"

VERSION=$(poetry version --short)
if [ -n "$VERSION" ]; then
  echo "Version: $VERSION"
else
    echo "Version not found."
    exit 1
fi

echo "Building code interpreter"
docker buildx build --platform "$PLATFORMS" \
  --tag "$REPOSITORY/$USER/$CODE_INTERPRETER_NAME:latest" \
  --tag "$REPOSITORY/$USER/$CODE_INTERPRETER_NAME:$VERSION" \
  --push .

echo "Building code executor"
cd "executor"
docker buildx build --platform "$PLATFORMS" \
  --tag "$REPOSITORY/$USER/$CODE_EXECUTOR_NAME:latest" \
  --tag "$REPOSITORY/$USER/$CODE_EXECUTOR_NAME:$VERSION" \
  --push .