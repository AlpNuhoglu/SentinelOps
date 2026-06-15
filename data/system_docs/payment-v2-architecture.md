# System Architecture: payment-v2

## Overview
payment-v2 is the core payment authorization and ledger service. It runs as a Kubernetes
Deployment with 3 replicas behind the api-gateway. Each pod holds an in-memory ledger
cache and a JDBC connection pool to the core banking database.

## Resource profile
- JVM heap: -Xmx512m (known to be tight under peak load)
- Readiness probe: HTTP /healthz, initialDelaySeconds=10
- HPA: min=3, max=10 replicas, target CPU 70%

## Known failure modes
- OOMKilled under sustained concurrency (unbounded ledger cache). Mitigation: ROLLBACK
  to the last good revision and/or SCALE replicas up.
- CrashLoopBackOff downstream of OOMKilled.

## Operational runbook references
- Rollback: `kubectl rollout undo deployment/payment-v2`
- Scale: `kubectl scale deployment/payment-v2 --replicas=N`
- Restart: delete the failing pod to let the Deployment reschedule it.
