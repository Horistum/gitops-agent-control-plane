# Single-host scheduling template

These systemd units wake one already initialized run with `agent-control tick`.
They do not create a product goal, approve a decision or provide a distributed
queue. Adjust the owner, installed executable, environment-file and run path.

1. Install the controller and trusted provider under the selected OS owner.
   Prepare that owner's Git transport and rootless Podman delegation first.
2. Create and validate the policy/goal outside the product. Initialize with
   `agent-control start --policy POLICY --goal GOAL --state RUN --max-steps 1`.
   Exit 2 is expected while an initialized goal still needs more ticks.
3. Place explicit model/GitHub environment credentials in an operator-managed
   environment file, or configure a protected credential broker. Use mode 0600;
   never commit the environment file. Do not log its contents.
4. Review and install both example unit files under `/etc/systemd/system`, then
   run `systemctl daemon-reload` and `systemctl enable --now agent-control-tick.timer`.
5. Inspect JSON in `journalctl -u agent-control-tick.service`, and use `status`,
   `decision` and `usage` under the same OS owner. Stop the timer before upgrades.

One tick may wait for its configured external/build deadline. Timer overlap is
avoided by systemd's oneshot service and additionally rejected by the writer lock.
Held or paused runs do not consume new model calls. A killed process may leave an
uncertain model outcome requiring explicit owner recovery; a timer cannot safely
assume that the provider was never charged. The generous unit timeout must remain
greater than the largest bounded phase in your configured workload.

With a system-level service, confirm rootless Podman/cgroup/user-runtime setup
for the configured owner on your host. These units do not provision delegation,
credentials, images, tenant isolation or monitoring. The existing `doctor` and
actual container lifecycle check remain required deployment checks.
