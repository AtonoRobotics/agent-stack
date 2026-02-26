# Fleet Management

## Network Setup
- All machines connected via Tailscale mesh VPN
- mDNS available on local network

## Machine Hostnames
| Machine     | Local Hostname       | Tailscale Hostname | SSH Command                      |
|-------------|---------------------|--------------------|----------------------------------|
| Workstation | localhost            | alpha-workstation  | (local)                          |
| DGX Spark   | spark-2b53.local     | alpha-dgx-spark    | ssh zero@spark-2b53.local        |
| AGX Thor    | alpha-agx-thor       | alpha-agx-thor     | ssh samuel@alpha-agx-thor        |
| Orin Nano   | alpha-orin-nano      | alpha-orin-nano    | ssh samuel@alpha-orin-nano       |

## DGX Spark Special Notes
- Locale fix may be needed: export LC_ALL=C
- Do NOT restart gdm3 (see hardware/dgx_spark.md)
- Ollama service managed by systemd

## Fleet Operations
1. Always check connectivity before batch operations
2. Run on one machine first, verify, then deploy to fleet
3. Never run destructive operations without explicit approval
4. Log all fleet-wide operations to activity_log
