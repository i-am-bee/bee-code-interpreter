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

import numpy as np
import pandas as pd
from scipy.stats import ttest_ind

# Generate some sample data
np.random.seed(42)
control_group = np.random.normal(loc=10, scale=2, size=100)
experimental_group = np.random.normal(loc=12, scale=2, size=100)

# Calculate mean and standard deviation using Pandas
control_mean = pd.Series(control_group).mean()
experimental_mean = pd.Series(experimental_group).mean()
control_std = pd.Series(control_group).std()
experimental_std = pd.Series(experimental_group).std()

print("Control Group Mean:", control_mean)
print("Experimental Group Mean:", experimental_mean)
print("Control Group Standard Deviation:", control_std)
print("Experimental Group Standard Deviation:", experimental_std)

# Perform a t-test using SciPy
t_statistic, p_value = ttest_ind(control_group, experimental_group)

print("T-Statistic:", t_statistic)
print("P-Value:", p_value)
