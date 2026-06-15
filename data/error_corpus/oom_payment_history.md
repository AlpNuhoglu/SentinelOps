# Incident History: payment-v2 OutOfMemoryError (OOMKilled)

## Symptoms / Log keys
- key=MEM_PRESSURE followed by key=OOM_KILL
- message: "java.lang.OutOfMemoryError: Java heap space"
- message: "container terminated reason=OOMKilled"
- followed by key=PROBE_FAIL and key=CRASHLOOP

## Root cause (confirmed)
The payment-v2 service leaks heap under sustained load because the in-memory ledger
cache is not bounded. When concurrent requests exceed the configured pool, the JVM heap
saturates and the kubelet OOM-kills the container, leading to CrashLoopBackOff.

## Proven remediation
1. Roll back payment-v2 to the previous known-good revision to restore service.
2. Horizontally scale replicas to absorb load while the fix is prepared.
Action taken in prior incidents: ROLLBACK target=payment-v2 (INC-2025-1187, INC-2026-0042).
