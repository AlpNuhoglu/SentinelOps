# Incident History: Readiness/Liveness probe failures

## Symptoms / Log keys
- key=PROBE_FAIL standalone (no preceding OOM)
- message: "readiness probe failed"

## Root cause (confirmed)
Transient probe failures caused by slow startup after deployment. The container is
healthy but exceeds the initialDelaySeconds window.

## Proven remediation
Restart the affected pod to re-trigger the probe sequence.
Action taken in prior incidents: RESTART target=affected-pod (INC-2025-0904).
