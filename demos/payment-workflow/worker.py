import asyncio, os
from concurrent.futures import ThreadPoolExecutor
from temporalio.client import Client
from temporalio.worker import Worker
import activities as A, workflows as W
async def main():
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "temporal:7233"))
    w = Worker(client, task_queue="payment-exceptions", workflows=[W.PaymentException], activities=[A.gather_facts, A.rules_gate, A.recommend, A.write_back, A.record_decision], activity_executor=ThreadPoolExecutor(8))
    print("worker ready, write-back mode:", A.WRITE_BACK, flush=True); await w.run()
asyncio.run(main())
