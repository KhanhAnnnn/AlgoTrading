import subprocess
import sys
import time
import requests

cmd = [
    "docker", "run", "--rm",
    "--network", "algotrading_algotradingenvju",
    "-v", "d:\\AlgoTrading\\ddl_production.sql:/tmp/ddl_production.sql",
    "algotrading-sql-client",
    "/opt/flink/bin/sql-client.sh", "embedded",
    "-l", "/opt/sql-client/lib",
    "-f", "/tmp/ddl_production.sql",
    "-Drest.address=jobmanager",
    "-Drest.port=8081",
    "-Djobmanager.rpc.address=jobmanager",
    "-Djobmanager.rpc.port=6123",
    "-Dexecution.attached=false"
]

print("Executing Flink SQL Client submission...")
res = subprocess.run(cmd, capture_output=True, text=True)
print("Return code:", res.returncode)
print("STDOUT:\n", res.stdout)
if res.stderr:
    print("STDERR:\n", res.stderr)

print("\nChecking Flink Jobs via REST API...")
time.sleep(2)
try:
    r = requests.get("http://localhost:8081/jobs/overview", timeout=5)
    print(r.json())
except Exception as e:
    print("Flink REST check error:", e)
