# Validation evidence

Generate reports from the exact revision being evaluated. Historical consumer
reports are not current release certification and may contain private product
identities; keep them in the consumer's private audit storage.

The public baseline is `./scripts/agentctl validate`, the actual rootless Podman
CI job, the installed operational lifecycle, and the publication source/package
checks. Reports must identify the commit, tools, tests, outcome, known limits,
and whether providers are controlled peers or live services.

`python3 scripts/check_distribution.py --output /absolute/private-audit/package-check`
records source/wheel hashes, backend version, license checks, installation and
CLI/core smoke tests. The history-scan workflow records fetched refs and redacted
findings. Neither result proves legal clearance or publication approval.

For a separately trusted consumer, use `scripts/check_consumer.py` with an exact
clean commit and an output path outside the consumer checkout. Its tests run in
a temporary copy; the consumer's activation and live-provider validation remain
separate. Never commit raw consumer logs, credentials, state directories, or
private product deployment records to this reference repository.
