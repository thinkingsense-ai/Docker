"""Wait for the Temporal server to accept connections. In the cloud pod Temporal starts beside the worker and the inbox, so they may come up first."""
import asyncio, os
from temporalio.client import Client

async def connect(tries=90, delay=2.0):
    addr = os.environ.get("TEMPORAL_ADDRESS", "temporal:7233"); last = None
    for _ in range(tries):
        try: return await Client.connect(addr)
        except Exception as e: last = e; await asyncio.sleep(delay)
    raise RuntimeError("Temporal at %s did not come up: %s" % (addr, last))
