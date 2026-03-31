import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio

from agent.operations.system import (
    EnvironmentOperations,
    ProcessOperations,
    ServiceOperations,
    SystemInfoOperations,
)


async def test():
    proc = ProcessOperations()
    svc = ServiceOperations()
    env = EnvironmentOperations()
    info = SystemInfoOperations()

    processes = await proc.list_processes(limit=5)
    print(f"Processes: {len(processes)} found")

    services = await svc.list_services()
    print(f"Services: {len(services)} found")

    vars = await env.list_variables(filter_name="PATH")
    print(f"Env vars with PATH: {len(vars)}")

    cpu_info = await info.get_cpu_info()
    print(f"CPU: {cpu_info.get('logical_cores', 'N/A')} cores, {cpu_info.get('cpu_percent', 'N/A')}%")

    print("All system operations working correctly!")


if __name__ == "__main__":
    asyncio.run(test())
