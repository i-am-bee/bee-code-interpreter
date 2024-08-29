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
docker manifest rm "$USER/$CODE_INTERPRETER_NAME" 2>/dev/null || true
docker build --progress=plain --platform "$PLATFORMS" --manifest "$USER/$CODE_INTERPRETER_NAME" .
docker manifest push "$USER/$CODE_INTERPRETER_NAME" "$REPOSITORY/$USER/$CODE_INTERPRETER_NAME:latest" --all
docker manifest push "$USER/$CODE_INTERPRETER_NAME" "$REPOSITORY/$USER/$CODE_INTERPRETER_NAME:$VERSION" --all

echo "Building code executor"
cd "executor"
docker manifest rm "$USER/$CODE_EXECUTOR_NAME" 2>/dev/null || true
docker build --progress=plain --platform "$PLATFORMS" --manifest "$USER/$CODE_EXECUTOR_NAME" .
docker manifest push "$USER/$CODE_EXECUTOR_NAME" "$REPOSITORY/$USER/$CODE_EXECUTOR_NAME:latest" --all
docker manifest push "$USER/$CODE_EXECUTOR_NAME" "$REPOSITORY/$USER/$CODE_EXECUTOR_NAME:$VERSION" --all