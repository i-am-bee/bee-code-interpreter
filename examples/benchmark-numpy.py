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

import numpy
import time

def cpu_intensive_computation():
    array_size = 10**8
    large_array = numpy.random.rand(array_size)
    result = numpy.sum(numpy.square(large_array))
    return result

start_time = time.time()
result = cpu_intensive_computation()
end_time = time.time()
print("Result:", result)
print("Execution Time:", end_time - start_time, "seconds")
