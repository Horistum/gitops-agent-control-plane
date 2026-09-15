# Goal reconciliation and repair

The outer reconciliation loop is what turns a bounded patch executor into an autonomous control plane. `COMPLETED` for one candidate is not automatically completion of the requested goal.

## Goal projection

At every reconciliation point the controller computes a machine projection containing:

- requested roadmap items;
- controller-recorded completed items;
- remaining items;
- currently eligible dependency-ready items;
- remaining items blocked by unsatisfied dependencies;
- `satisfied`, derived from requested items versus release-state completion.

The human-readable `goal.success_condition` is reasoning context. It is not parsed as an executable predicate in `autonomous-control-plane/v1`. `goal-evaluation.satisfied` is the machine completion projection.

## Work selection

Only an item that is all of the following may be selected:

1. explicitly requested by goal intent;
2. present in validated roadmap authority;
3. marked `ready`;
4. not already controller-recorded complete;
5. dependency-ready according to validated release state.

If requested work remains but no authorized dependency-ready item exists, the controller fails closed rather than inventing work outside roadmap authority.

## Preconditions per cycle

Before the first proposal attempt for an item, the controller runs:

- protected diagnostic baseline tests;
- baseline verification probes plus all acceptance probes promoted from previously completed items;
- a case-level negative control proving the selected item's new acceptance behavior is not already satisfied by the current baseline.

These checks are bound to the current Git base.

## Repair feedback

Candidate verification failure can persist blocking findings and route a bounded developer repair attempt instead of immediately terminating. Attempt and cycle budgets are the minimum of product policy and goal authority.

A repair attempt is not permission to reuse stale verification context. Human `request_changes` therefore reruns the same baseline/regression/negative-control preconditions against the current `main` revision before the next proposal. `retry-preconditions-<item>-attempt-XX.json` records the base SHA and each precondition result.

## Candidate history

Transient candidate branches may be removed during repair, rejection, or cleanup, but each committed candidate is retained by an evidence tag under `refs/tags/evidence/candidates/...`. The exact object named by candidate evidence therefore remains reachable for later audit.

## Verified progress

After exact post-merge verification, release-state advancement is a second durable controller effect. The controller first persists a `control-state` intent containing:

- item identity;
- exact verified merge SHA;
- desired release-state content;
- desired-state digest;
- stable `Control-State-Id`.

Only then is `.agent-control/release-state.json` committed. The consume step rereads the observed state and requires its digest to equal the durable intent before progress is accepted.

## Recovery boundaries

If the process terminates before effect receipt consumption, a fresh process can locate the Git effect by stable trailer identity, verify it, avoid duplication, and continue.

Durability also covers crashes after an effect has been consumed. `POSTMERGE_VERIFY` is safely replayable against the already-recorded exact merge SHA. `RECONCILE` is safely continuable from controller-owned release state with no pending side effect. `phase-recovery.json` records the phase and replay/continue action.

The controller stops only when the requested item projection is satisfied or when policy, authority, or bounded autonomy prevents further progress.
