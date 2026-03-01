# CR10 Safety System Architecture — Design Document

## 1. Mission Statement

The safety system protects humans and equipment during CR10 cinema camera robot operation by:
1. Continuously monitoring the workspace for human presence using depth cameras + NvBlox
2. Classifying proximity into safety zones (NORMAL / WARNING / STOP / ESTOP)
3. Modulating robot speed or triggering protective stops based on zone classification
4. Providing an independent safety layer that operates regardless of the motion pipeline state

**The safety system is the LAST gate before commands reach the robot driver.**

## 2. Architecture Overview

```
                    ┌─────────────────────────────────────┐
                    │         PERCEPTION LAYER             │
                    │                                      │
                    │  ZED-X Camera(s)                     │
                    │    ├─ Depth (30Hz+)                  │
                    │    ├─ RGB                            │
                    │    ├─ Body Tracking                  │
                    │    └─ IMU + Pose                     │
                    │           │                          │
                    │  NvBlox (GPU, Docker)                │
                    │    ├─ TSDF Reconstruction            │
                    │    ├─ ESDF Distance Field            │
                    │    ├─ People Segmentation Layer      │
                    │    └─ Dynamic Object Layer           │
                    └──────────────┬──────────────────────┘
                                   │
                         ESDF + Human Occupancy
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         SAFETY DECISION LAYER        │
                    │                                      │
                    │  Safety Monitor Node (ROS2)          │
                    │    ├─ Query ESDF at robot links      │
                    │    ├─ Compute min distance to human  │
                    │    ├─ Classify zone (SSM formula)    │
                    │    ├─ Compute speed factor            │
                    │    └─ Publish safety state            │
                    │                                      │
                    │  Watchdog Timer                       │
                    │    ├─ Heartbeat from perception       │
                    │    ├─ If no heartbeat → ESTOP         │
                    │    └─ If stale data → STOP            │
                    └──────────────┬──────────────────────┘
                                   │
                         SafetyState message
                         (zone, speed_factor, distances)
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         ENFORCEMENT LAYER            │
                    │                                      │
                    │  Safety Enforcer (safety_enforcer.py)│
                    │    ├─ Receives trajectory commands    │
                    │    ├─ Receives SafetyState            │
                    │    ├─ Scales velocities by factor     │
                    │    ├─ Enforces joint velocity limits  │
                    │    ├─ Triggers protective stop        │
                    │    ├─ Manages E-stop state machine    │
                    │    └─ Forwards safe commands only     │
                    │                                      │
                    │  Command Validator                    │
                    │    ├─ Joint limit checking             │
                    │    ├─ Workspace boundary check         │
                    │    ├─ Payload validation               │
                    │    └─ Singularity proximity check      │
                    └──────────────┬──────────────────────┘
                                   │
                         Validated, speed-limited commands
                                   │
                    ┌──────────────▼──────────────────────┐
                    │         ROBOT DRIVER                  │
                    │  (TCP async driver, 100Hz feedback)   │
                    └─────────────────────────────────────┘
```

## 3. Components Detail

### 3.1 Perception Layer (Isaac ROS Docker)

**NvBlox Node Configuration:**
```yaml
nvblox_node:
  ros__parameters:
    voxel_size: 0.05                    # 5cm voxels (balance: resolution vs GPU)
    mapping_type: "human_with_static_tsdf"  # People separation enabled
    integrate_depth_rate_hz: 30         # Match camera framerate
    update_esdf_rate_hz: 10             # 10Hz distance field (100ms latency)
    decay_dynamic_occupancy_rate_hz: 5  # People fade after leaving FOV
    esdf_integrator_max_distance_m: 3.0 # 3m ESDF range (covers all safety zones)
    projective_integrator_max_integration_distance_m: 5.0
    map_clearing_radius_m: 4.0
```

**Published Topics:**
| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/nvblox/esdf_pointcloud` | PointCloud2 | 10Hz | ESDF distance field |
| `/nvblox/human_esdf_pointcloud` | PointCloud2 | 10Hz | Human-only ESDF |
| `/nvblox/mesh` | Mesh | 1Hz | Visual mesh for dashboard |
| `/nvblox/costmap` | OccupancyGrid | 10Hz | 2D costmap |

**Required Inputs:**
| Topic | Source | Rate |
|-------|--------|------|
| `/zed/depth/depth_registered` | ZED-X | 30Hz |
| `/zed/rgb/image_rect_color` | ZED-X | 30Hz |
| `/zed/pose` | ZED-X VSLAM | 30Hz |
| `/zed/human_mask` | Segmentation model | 15Hz |

### 3.2 Safety Decision Layer (Safety Monitor Node)

**Core Logic:**
1. Subscribe to NvBlox ESDF and human occupancy
2. Get current robot joint positions from driver feedback
3. Compute forward kinematics → link positions in world frame
4. Query ESDF at each link position → minimum distance to nearest obstacle/human
5. Apply SSM formula to compute protective distance
6. Classify zone and compute speed factor
7. Publish SafetyState at 50Hz

**SafetyState Message:**
```
# SafetyState.msg
Header header
string zone          # NORMAL / WARNING / STOP / ESTOP / SENSOR_FAULT
float64 speed_factor # 0.0 (stopped) to 1.0 (full speed)
float64 min_human_distance_m
float64 min_obstacle_distance_m
float64[] link_distances  # Per-link minimum distances (7 values)
bool perception_healthy   # False if sensor data stale
bool estop_active
string reason             # Human-readable explanation
```

**Zone Thresholds (configurable):**
```yaml
safety_zones:
  estop_distance_m: 0.2    # Hard brake, immediate
  stop_distance_m: 0.5     # Controlled stop (STOP 2)
  warning_distance_m: 1.5  # Linear speed ramp
  normal_distance_m: 1.5   # Full speed above this
  sensor_timeout_ms: 500   # Stale data → STOP
  heartbeat_timeout_ms: 1000 # No data → ESTOP
```

**SSM Calculation (simplified for our system):**
```python
# Protective distance (ISO/TS 15066 simplified)
S_min = v_human * T_response + v_robot * T_stop + C + Z_sensor + Z_robot

# Our values:
# v_human = 2.0 m/s (conservative, ISO 13855)
# T_response = 0.15s (NvBlox 10Hz + processing)
# v_robot = current TCP velocity (from FK + Jacobian)
# T_stop = 0.3s (controlled deceleration)
# C = 0.1m (intrusion distance)
# Z_sensor = 0.05m (ZED-X depth uncertainty at 2m)
# Z_robot = 0.02m (encoder uncertainty)

# At zero robot speed: S_min ≈ 0.47m → matches our 0.5m stop zone
# At 0.5 m/s robot speed: S_min ≈ 0.62m → within warning zone
```

### 3.3 Enforcement Layer

**Safety Enforcer** — the gatekeeper between pipeline and driver:
```
Input:  JointTrajectory (from cuRobo smoother)
Input:  SafetyState (from safety monitor)
Output: Validated, speed-limited JointCommand (to robot driver)
```

**State Machine:**
```
                NORMAL
                  │
          human approaches
                  │
                  ▼
               WARNING ──── speed_factor applied
                  │
          human closer
                  │
                  ▼
                STOP ────── controlled deceleration
                  │
          human very close / sensor fault
                  │
                  ▼
                ESTOP ───── hard brake + disable
                  │
          human cleared + manual reset
                  │
                  ▼
              RECOVERY ──── slow re-enable
                  │
          all clear confirmed
                  │
                  ▼
                NORMAL
```

**E-stop requires manual reset** — the system does NOT auto-resume from ESTOP. This prevents cycling between ESTOP/NORMAL if a human is at the boundary.

**Command Validator** checks (independent of safety monitor):
- Joint positions within URDF limits
- TCP position within workspace envelope (1525mm reach)
- Joint velocities within limits × speed_factor
- Payload within 10kg limit
- No consecutive identical commands (watchdog)

### 3.4 Watchdog System
- **Perception heartbeat:** If no ESDF update in 500ms → zone = STOP
- **Perception dead:** If no ESDF update in 1000ms → zone = ESTOP
- **Driver heartbeat:** If no feedback from robot in 200ms → zone = ESTOP
- **Self-check:** Safety monitor publishes its own heartbeat; enforcer monitors it
- **Dual-channel:** Safety enforcer and safety monitor are separate processes

## 4. Data Flow Summary

```
ZED-X → NvBlox (Docker, ESDF) → Safety Monitor (zone, speed_factor)
                                          │
Cinema Spline → IK → cuRobo → ──────────▶ Safety Enforcer → Robot Driver
                                          │
                                 Command Validator
```

## 5. Failure Modes and Mitigations

| Failure | Detection | Response |
|---------|-----------|----------|
| Camera disconnected | No depth data | ESTOP after 1s |
| NvBlox crash | No ESDF updates | STOP after 500ms, ESTOP after 1s |
| Safety monitor crash | No SafetyState | Enforcer defaults to ESTOP |
| Network partition (ROS2) | Missing heartbeats | ESTOP |
| GPU overheated | NvBlox slowdown | Reduced ESDF rate, WARNING zone expands |
| False positive (object = person) | N/A | Unnecessary stop (safe, acceptable) |
| False negative (person missed) | SOTIF testing | Multi-camera, conservative zones |
| Robot driver crash | No feedback | ESTOP (hardware watchdog on driver) |

## 6. Implementation Phases

### Phase 1: Software Safety Enforcer (no perception)
- Command validator (joint limits, workspace, velocity)
- Speed limiting from manual SafetyState input
- E-stop state machine
- Dashboard integration (safety status display)
- **Runs on host, no Docker needed**

### Phase 2: NvBlox Perception Pipeline
- ZED-X → NvBlox in Isaac ROS Docker
- ESDF publishing and visualization
- People detection mode
- **Runs in Docker, ROS2 bridge to host**

### Phase 3: Safety Monitor Integration
- ESDF → zone classification
- SSM formula implementation
- Automatic speed modulation
- Watchdog timers
- **Full loop: perception → decision → enforcement**

### Phase 4: Validation and Hardening
- Isaac Sim testing with synthetic humans
- Edge case testing (SOTIF scenarios)
- Multi-camera support
- Performance tuning (latency budget)
- Safety report generation

## 7. Hardware Requirements

### Minimum (Phase 1-2)
- 1× ZED-X camera (already have ZED SDK in Docker)
- RTX 4070 SUPER (12GB VRAM — sufficient for NvBlox + cuRobo)
- Isaac ROS Docker (already built)

### Recommended (Phase 3-4)
- 2× ZED-X cameras (eliminate blind spots)
- Infrastructure-mounted camera (Halos-style outside-in)
- Physical E-stop button wired to robot controller
- UPS for controlled shutdown

## 8. ROS2 Node Graph

```
/zed_node ────────┬──── /depth ────────► /nvblox_human_node
                  ├──── /rgb ──────────►       │
                  └──── /pose ─────────►       │
                                               │
/segmentation_node ── /human_mask ─────►       │
                                               │
                                    /esdf ─────► /safety_monitor_node
                                    /human_esdf ►       │
                                                        │
/robot_driver ── /joint_states ────────────────►       │
                                                        │
                                         /safety_state ►/safety_enforcer_node
                                                        │
/cinema_pipeline ── /joint_trajectory ─────────►       │
                                                        │
                                         /joint_command ► /robot_driver
```
