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

ROOT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && cd .. && pwd )

STORAGE_PATH=${APP_FILE_STORAGE_PATH:-"$ROOT_DIR/.tmp/files"}
mkdir -p "$STORAGE_PATH"

if [[ ! "$STORAGE_PATH" || ! -d "$STORAGE_PATH" ]]; then
  echo "Could not create storage directory"
  exit 1
fi

IMAGES_DIR="$ROOT_DIR/.tmp/images"
mkdir -p "$IMAGES_DIR"
if [[ ! "$IMAGES_DIR" || ! -d "$IMAGES_DIR" ]]; then
  echo "Could not create docker images directory"
  exit 1
fi

IMAGE_NAME="${APP_EXECUTOR_IMAGE:-localhost/bee-code-interpreter-executor:local}"

echo "Building image"
docker build --progress=plain -t "$IMAGE_NAME" executor

IMAGE_HASH=$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE_NAME" | md5sum | awk '{print $1}')
IMAGE_FILENAME="$IMAGE_HASH.tar"
IMAGE_OUTPUT_PATH="$IMAGES_DIR/$IMAGE_FILENAME"

if [ ! -f "$IMAGE_OUTPUT_PATH" ]; then
  echo "Dumping image"
  docker save "$IMAGE_NAME" -o "$IMAGE_OUTPUT_PATH"
  echo "Image has been saved to $IMAGE_OUTPUT_PATH"
else
  echo "Dumped image already exists and has same hash. Skipping."
fi

echo "Removing old images (if any)"
ls "$IMAGES_DIR" | grep -xv "${IMAGE_FILENAME}" | xargs -I {} sh -c "echo \"Deleting {}\" && rm \"$IMAGES_DIR/{}\""
