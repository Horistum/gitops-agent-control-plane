# Policy

`config/reference-policy.json` is contract v3 policy.

## Actor-specific write envelopes

The developer may write implementation source:

```json
"developer_allowed_paths": ["src/**"]
```

The independent tester may add only new acceptance-test files:

```json
"tester_allowed_paths": ["tests/test_acceptance_*.py"]
```

Protected baseline tests are owner-controlled:

```json
"protected_test_paths": ["tests/test_service.py"]
```

Product authority/verification infrastructure is separately snapshotted:

```json
"authority_paths": [".agent-control/**", "ci/**", ".github/**"]
```

The same segment-aware matcher is used for every path category.

## Structured forbidden paths

The goal contains `forbidden_paths`; product authority contains structured forbidden-path rules. These are executable policy inputs.

Free-form `forbidden_directions` remains explanatory text. It is not represented as magically machine-enforceable natural language. Likewise `authority.md` and `architecture.md` are owner-authored context included in the immutable authority snapshot; executable enforcement comes from the structured policy and authority documents.

## Risk

Risk rules are ordered by severity and can produce LOW, MEDIUM or HIGH:

- contract paths -> MEDIUM;
- security paths -> HIGH;
- otherwise policy default -> LOW.

`**` matches zero or more path segments, so both `src/security/x.py` and `src/a/security/x.py` match `src/**/security/**`.

Owner risk ceiling, automatic-merge ceiling and policy human-gate threshold are independent controls.

## Budgets

Changed-file count and patch bytes are evaluated before candidate workspace mutation. A blocked budget therefore creates no candidate side effect.

Conformance exercises both limits independently: one scenario exceeds the changed-file limit, while `patch-budget-exceeded` stays within the file-count limit and exceeds only `max_patch_bytes`.
