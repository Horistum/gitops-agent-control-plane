# Linux guide

The standalone showcase needs only:

- Bash;
- Git;
- Python 3.11+;
- roughly 1 GiB free disk for comfortable experimentation.

Check:

```bash
./scripts/agentctl bootstrap check
```

Prepare supported Debian/Ubuntu or Fedora/RHEL-family systems:

```bash
./scripts/agentctl bootstrap prepare
```

Run:

```bash
./scripts/agentctl validate
./scripts/agentctl demo happy-path
./scripts/agentctl demo all
```

Diagnostics:

```bash
./scripts/agentctl diagnose
```

Remove only local demo artifacts:

```bash
./scripts/agentctl cleanup
```

No daemon, rootless container setup, credentials or external model CLI are required.
