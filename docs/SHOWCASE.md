# Executable showcase

Run `./scripts/agentctl loop` for the central v7 demo. It selects EXAMPLE-001, verifies/merges it, records controller-owned release state, reconciles, unlocks EXAMPLE-002, carries the first item's acceptance probes forward as regressions, and stops only after both requested items complete.

`repair-loop` demonstrates verification feedback and a second bounded attempt. `human-approve-resume` demonstrates durable human authority. `dependency-blocked` demonstrates refusal to invent undeclared dependency work. All v6 verification/security regressions remain in the matrix.
