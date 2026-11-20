import asyncio, os
from concurrent.futures import ThreadPoolExecutor
import temporal_wait
from temporalio.worker import Worker
import activities as A, workflows as W, it_workflow as IW, rca_workflow as RW
async def main():
    client = await temporal_wait.connect()
    w = Worker(client, task_queue="payment-exceptions", workflows=[W.PaymentException, IW.VulnerabilityException, RW.IncidentClusterRca], activities=[A.gather_facts, A.rules_gate, A.sap_gather_facts, A.sap_rules_gate, A.recommend, A.write_back, A.record_decision, A.it_gather_facts, A.it_rules_gate, A.it_recommend, A.it_write_back, A.rca_gather_facts, A.rca_rules_gate, A.rca_recommend, A.rca_write_back], activity_executor=ThreadPoolExecutor(8))
    print("worker ready, write-back mode:", A.WRITE_BACK, flush=True); await w.run()
asyncio.run(main())
