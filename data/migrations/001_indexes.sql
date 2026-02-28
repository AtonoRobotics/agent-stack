-- Add indexes on common query filters
CREATE INDEX IF NOT EXISTS idx_fleet_health_machine_ts ON fleet_health(machine, timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent ON agent_tasks(agent);
CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_perf_metrics_robot_metric ON performance_metrics(robot_serial, metric_name);
