import time

async def wait_for_result(delay: float) -> str:
    time.sleep(delay)
    return "ready"
