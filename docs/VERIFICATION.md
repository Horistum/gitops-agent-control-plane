# Verification matrix

The reference distinguishes **offline contract verification** from **live environment verification**. Both matter, and neither should be mislabeled as the other.

## Layer A: repository CI

Run:

```bash
python3 scripts/validate_reference.py
```

The script verifies:

| Check | Proof |
|---|---|
| Example baseline | executes the real product test runner |
| Test discovery | requires executed tests |
| JUnit evidence | parses generated XML and requires testcase identities |
| Portable authority layout | requires `.agent-control/*` files and keeps them outside write paths |
| Policy renderer | renders a complete tenant policy in a temporary directory |
| Policy identity | confirms product/control separation and CI identity consistency |
| Goal adapter | builds backend protocol from portable goal JSON without GitHub writes |
| Operator adapter | maps every generic owner command to one exact backend message |
| Governance renderer | validates ruleset structure and trusted check binding |
| Compatibility pin | requires exact runtime commit and version |
| Python syntax | compiles reference scripts and example code |
| Backend-neutral narrative | rejects concrete backend branding in README and core docs |

GitHub Actions runs the same script on every pull request.

## Layer B: installation preflight

`scripts/install_runtime.py` additionally verifies on the target host:

- repository access and product/control separation;
- private control repository and enabled Issues;
- default branch and command issue;
- required executables and rootless container support;
- exact pinned runtime commit;
- runtime Git tree versus release manifest;
- SHA-256 of manifest files;
- absence of extra files in an existing immutable runtime installation;
- runtime unit tests and doctor/preflight;
- real model protocol smoke unless explicitly skipped;
- real isolated product baseline unless explicitly skipped.

Skip flags exist for diagnosis, not to redefine an installation as proven.

## Layer C: first live goal

The first live goal proves the lifecycle static CI cannot:

1. goal accepted from the owner adapter;
2. `EXAMPLE-001` discovered from product authority;
3. candidate implementation created;
4. deterministic tests execute and produce identities;
5. independent review evidence exists;
6. product pull request is created on the exact candidate SHA;
7. trusted CI succeeds for that candidate;
8. merge occurs under configured authority;
9. trusted post-merge CI succeeds on the merge SHA;
10. completion is persisted in remote state.

The example is intentionally small so every artifact can be inspected manually.

## What repository CI does not prove

Repository CI does not prove that a future adopter has valid credentials, model subscription/session, rootless container support, a correct test image, repository administration privileges, a reachable compatible runtime source or live CI capacity. Those are live preflight properties and are tested where they actually exist.
