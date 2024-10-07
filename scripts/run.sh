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
docker build -t localhost/bee-code-interpreter:local .
docker build -t localhost/bee-code-executor:local executor
kubectl delete -f k8s/local.yaml || true
kubectl apply -f k8s/local.yaml
kubectl wait --for=condition=Ready pod/code-interpreter-service
kubectl port-forward pods/code-interpreter-service 50051:50051 &
kubectl logs --follow code-interpreter-service
wait