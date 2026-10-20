#!/usr/bin/env python3
"""No API calls: verify one Ray actor can start on the target host."""
import os

for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'

import ray

ray.init(include_dashboard=False, num_cpus=1, object_store_memory=80000000)


@ray.remote
class Probe:
    def ping(self):
        return 'ray_actor_ok'


try:
    actor = Probe.remote()
    print(ray.get(actor.ping.remote(), timeout=120), flush=True)
finally:
    ray.shutdown()
