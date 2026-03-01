# CR10 Safety System — Implementation Plan

## Phase 1: Software Safety Enforcer (No Perception)
**Sprint scope:** Within `~/dobot_cr10/` (allowed by SPRINT-002)
**Dependencies:** None (runs standalone)
**Deliverables:**
- [ ] `safety/command_validator.py` — joint limits, velocity, workspace checks
- [ ] `safety/safety_enforcer.py` — speed limiting, E-stop state machine
- [ ] `safety/safety_state.py` — SafetyState dataclass and ROS2 message definition
- [ ] Unit tests for command validator and state machine
- [ ] Dashboard integration — safety status widget on Robot page

**How it works (Phase 1):**
```
Cinema Pipeline → cuRobo → Command Validator → Safety Enforcer → Robot Driver
                                                     ↑
                                            Manual SafetyState
                                         (dashboard or CLI input)
```

## Phase 2: NvBlox Perception Pipeline
**Sprint scope:** Requires `~/workspaces/isaac_ros-dev/` access
**Dependencies:** ZED-X camera (or simulated depth in Isaac Sim)
**Deliverables:**
- [ ] NvBlox launch config for human-aware mapping (config already created)
- [ ] ZED-X → NvBlox topic remapping and bringup launch file
- [ ] ESDF visualization in RViz / dashboard
- [ ] People detection validation (precision/recall metrics)
- [ ] Simulated testing: Isaac Sim synthetic depth → NvBlox

**How it works (Phase 2):**
```
ZED-X → NvBlox (Docker) → ESDF + Human Occupancy → Published to ROS2
```

## Phase 3: Safety Monitor Integration
**Sprint scope:** Requires `safety/` directory access (human approval needed)
**Dependencies:** Phase 1 + Phase 2
**Deliverables:**
- [ ] `safety/safety_monitor.py` — ESDF query, FK, zone classification, SSM formula
- [ ] Forward kinematics module (compute link positions from joint state)
- [ ] ESDF querying (point lookup in NvBlox distance field)
- [ ] Watchdog timers (perception heartbeat, driver heartbeat)
- [ ] Integration test: end-to-end perception → decision → enforcement

**How it works (Phase 3):**
```
ZED-X → NvBlox → Safety Monitor → SafetyState → Safety Enforcer → Driver
                       ↑
                  Joint States
                 (robot feedback)
```

## Phase 4: Validation and Hardening
**Sprint scope:** All safety directories
**Dependencies:** Phase 3
**Deliverables:**
- [ ] Isaac Sim validation: synthetic humans, edge cases, SOTIF scenarios
- [ ] Multi-camera support (2× ZED-X, eliminate blind spots)
- [ ] Performance profiling (latency budget: camera → ESDF → zone → command)
- [ ] Safety report generation (automated from test results)
- [ ] Documentation: operator manual for safety system

## Tools Available (agents/tools.py)
| Tool | Description |
|------|-------------|
| `safety_check_perception` | Check NvBlox Docker container status |
| `safety_check_zones` | Read zone config and report status |
| `safety_get_architecture` | Return architecture document |
| `safety_list_knowledge` | List all safety knowledge base docs |
| `safety_validate_trajectory` | Validate trajectory against joint/velocity limits |

## Skills Available (skills/safety.py)
| Skill | Description |
|-------|-------------|
| `safety_monitor_node` | Generate ROS2 safety monitor node skeleton |
| `safety_enforcer_node` | Generate ROS2 safety enforcer node skeleton |
| `nvblox_launch_config` | Generate NvBlox launch file for safety perception |
| `workspace_test` | Generate workspace boundary validation test |
| `velocity_test` | Generate velocity limit validation test |
| `payload_test` | Generate payload validation test |
| `estop_test` | Generate E-stop validation test |
| `human_proximity_test` | Generate human proximity safety test |
| `safety_report` | Generate comprehensive safety validation report |

## Knowledge Base (knowledge/safety/)
| Document | Content |
|----------|---------|
| `nvblox_reference.md` | NvBlox technical details, parameters, performance |
| `halos_reference.md` | NVIDIA Halos architecture, zone monitoring, compliance |
| `zed_x_reference.md` | ZED-X camera specs, depth sensing, ROS2 topics |
| `safety_standards_reference.md` | ISO 10218, 15066, 13849, 21448 (SOTIF) |
| `safety_system_architecture.md` | Full architecture design with diagrams |
| `implementation_plan.md` | This document |

## Risk Register
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| False negative (person not detected) | Medium | Critical | Multi-camera, conservative zones, SOTIF testing |
| NvBlox GPU memory exhaustion | Low | High | Voxel size tuning, map clearing radius |
| Latency spike (>500ms) | Medium | High | Watchdog → STOP, performance profiling |
| ZED-X failure (cable, overheating) | Low | Critical | Watchdog → ESTOP, physical E-stop backup |
| Network partition (ROS2 DDS) | Low | High | Local-only DDS, heartbeat monitoring |
| Reflective surfaces confusing depth | Medium | Medium | Neural depth, occupancy decay |

## Next Steps
1. **Human approval needed:** Create `/safety/` directory (currently forbidden by sprint scope + Immutable Rule 1)
2. **Phase 1 can begin** in `~/dobot_cr10/cinema/` as part of pipeline integration (command validator + enforcer logic)
3. **Phase 2 can begin** by testing NvBlox in Isaac ROS Docker with simulated depth data
