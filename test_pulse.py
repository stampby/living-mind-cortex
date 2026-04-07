import asyncio
from core.runtime import runtime
from cortex.engine import cortex

async def run_test():
    await cortex.connect()
    print("Testing pulse 30 hook...")
    runtime.event_loops = 30
    try:
        await runtime._execute_phases("TEST")
    except Exception as e:
        print(f"Error: {e}")
    await cortex.disconnect()

asyncio.run(run_test())
