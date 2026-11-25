"""
submit_crypto_flink_job.py — Submits ddl_crypto.sql to Apache Flink cluster.
"""
import subprocess
import sys
import time
import requests

cmd = [
    "docker", "run", "--rm",
    "--network", "algotrading_algotradingenvju",
    "-v", "D:\\AlgoTrading\\ddl_crypto.sql:/tmp/ddl_crypto.sql",
    "algotrading-sql-client",
    "/opt/flink/bin/sql-client.sh", "embedded",
    "-l", "/opt/sql-client/lib",
    "-f", "/tmp/ddl_crypto.sql",
    "-Drest.address=jobmanager",
    "-Drest.port=8081",
    "-Djobmanager.rpc.address=jobmanager",
    "-Djobmanager.rpc.port=6123",
    "-Dexecution.attached=false"
]

print("Submitting Crypto Flink SQL streaming job...")
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:\n", res.stdout)
if res.stderr:
    print("STDERR:\n", res.stderr)

print("\nQuerying Flink REST API for active jobs...")
time.sleep(3)
try:
    r = requests.get("http://localhost:8081/jobs/overview", timeout=5)
    data = r.json()
    jobs = data.get("jobs", [])
    print(f"Total jobs: {len(jobs)}")
    for j in jobs:
        print(f"  - JID: {j['jid']} | Name: {j['name']} | State: {j['state']} | Tasks: {j['tasks']['running']}/{j['tasks']['total']}")
except Exception as e:
    print("Error querying Flink:", e)

