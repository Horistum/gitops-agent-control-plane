# Security model

## Primary threat

The dangerous failure mode is not merely a bad patch. It is a bad patch combined with enough authority to redefine the evidence proving that the patch was acceptable.

The design therefore focuses on authority separation and evidence provenance.

## Untrusted model sessions

Model sessions are proposal generators. They do not receive privileged repository credentials, do not directly merge changes and do not become the component applying arbitrary shell commands.

Repository text is treated as untrusted data. Prompt injection in source must not create a route to new tools or credentials.

## Narrow mutation surface

Only the controller applies proposed edits. Every path is checked against policy and runtime hard denies, and architecture-selected working sets narrow the envelope again.

Lifecycle actions are controller-owned and tied to a specific task/candidate identity.

## Deterministic execution isolation

Local product commands should run in rootless containers with no network, dropped capabilities, no-new-privileges, bounded memory/CPU/PIDs, read-only container root, explicit writable workspace, no inherited model/repository credential set and a pinned local image digest.

The test image is trusted execution infrastructure and must not float by tag.

## CI spoof resistance

A green string with the expected check name is insufficient. Policy binds the expected application identity and the runtime checks the exact commit SHA whose checks are consumed. Post-merge verification repeats that relation on the merge SHA.

## State integrity

Execution state uses a dedicated remote branch with one controller identity, non-force writes, monotonically increasing sequence, hash-linked events, immutable receipts and explicit pending-effect identity.

A failed state push is not treated as success. Remote state must be reconciled before another effect.

## Replay resistance

Receipts carry enough identity to reject stale evidence across runtime/policy activation, task phase, base/candidate SHA and request hash. Reusing old evidence merely because the task name matches is forbidden.

## Owner commands

The portable operator interface is `scripts/control.py`. The adapter translates explicit owner verbs to the active backend protocol. This translation does not broaden authority.

## Goal immutability

`scripts/submit_goal.py` creates a goal request from a portable JSON document. The backend records exact source identity; later server-side edits are not silently treated as authorization changes.

## Secrets

Do not commit tokens, provider credentials, repository credentials, copied credential homes, controller state directories or machine-specific policy containing sensitive operational details.

Use dedicated credential homes and pass only the minimum environment into child processes.

## Threats deliberately not solved

The reference is not a substitute for compromised organization administration, compromised host root, malicious trusted CI application, malicious pinned test image, distributed multi-writer consensus or formal verification of model reasoning.

Those boundaries are documented rather than disguised as generic “AI safety”.
