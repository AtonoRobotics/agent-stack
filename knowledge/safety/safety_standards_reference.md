# Robot & AV Safety Standards — Reference for CR10 Safety System

## Standards Hierarchy

### ISO 10218 (2025 Update) — Robot Safety Requirements
- **Part 1:** Robot design safety requirements
- **Part 2:** Robot system integration safety
- Now incorporates former ISO/TS 15066 collaborative robot guidance
- Defines four safe interaction methods:
  1. **Safety-rated monitored stop** — robot stops when human enters workspace
  2. **Hand guiding** — human physically guides robot
  3. **Speed and separation monitoring (SSM)** — our primary method
  4. **Power and force limiting** — inherently safe forces

### ISO/TS 15066 — Collaborative Robot Safety (now part of ISO 10218)
- Defines the **protective distance formula** for SSM
- Specifies force/pressure limits for power-and-force limiting
- Our CR10 uses SSM since it's a 10kg industrial arm (not inherently force-limited)

### ISO 13849 — Safety of Machinery Control Systems
- Performance Levels (PL a–e) for safety functions
- Our system targets **PL d** for development (PL e for production)
- Applies to: E-stop, safety monitoring, protective stops

### IEC 62443 — Industrial Cybersecurity
- Relevant for networked robot safety systems
- Secure communication between safety components
- Applies to: ROS2 DDS security, dashboard access control

### ISO 21448 (SOTIF) — Safety of Intended Functionality
- Addresses hazards from **system limitations** (not failures)
- Critical for perception-based safety:
  - Sensor misinterpretation (false negatives)
  - AI edge cases (hallucinated or missed detections)
  - Environmental conditions degrading perception
- Our system must address: known unsafe + unknown unsafe scenarios

### ISO 26262 / ISO/PAS 8800 — Functional Safety (AI Extension)
- Hardware/software integrity requirements
- ISO/PAS 8800 (2025) extends to AI components in safety systems
- Applicable to our NvBlox + ML-based human detection pipeline

## Speed and Separation Monitoring (SSM) — Technical Detail

### Protective Distance Formula (ISO/TS 15066)
```
S(t₀) ≥ S_h + S_r + S_s + C + Z_s + Z_r
```

Where:
- **S_h** = Human travel distance during system response time
  - Conservative: v_h = 2000mm/s (ISO 13855 worst case)
  - Measured: v_h = 1600mm/s when separation > 500mm
- **S_r** = Robot travel distance during response time
  - Computed from: joint velocities × Jacobian → TCP velocity
- **S_s** = Robot stopping distance after braking initiated
  - Depends on: payload %, configuration, stop category
- **C** = Intrusion distance (sensor-dependent, 0–1200mm)
- **Z_s** = Sensor position uncertainty
- **Z_r** = Robot position uncertainty

### NIST Reference Implementation
- Response time measured: **T_R = 0.113s** (±0.019s at 99.9% CI)
- Recommended update frequency: **≥100Hz**
- All joints require independent protective distance monitoring

### Zone Classification (Our Design)
| Zone | Distance | Action | Speed Factor |
|------|----------|--------|-------------|
| **NORMAL** | ≥ 1.5m | Full speed | 1.0 |
| **WARNING** | 0.5–1.5m | Reduced speed | Linear ramp 0→1 |
| **STOP** | < 0.5m | Immediate stop | 0.0 |
| **ESTOP** | < 0.2m | Emergency stop | 0.0 (hard brake) |

### Stop Categories (IEC 60204-1)
- **STOP 0** — Immediate power removal (uncontrolled)
- **STOP 1** — Controlled deceleration, then power off
- **STOP 2** — Controlled deceleration, power maintained (monitored standstill)

Our system uses:
- STOP 2 for WARNING→STOP transitions (controlled deceleration)
- STOP 1 for ESTOP (decelerate then disable)
- STOP 0 as hardware backup (physical E-stop button)

## SOTIF Application to Our System

### Known Unsafe Scenarios (must be mitigated)
- Person behind robot (camera blind spot) → need multi-camera or infrastructure sensor
- Transparent objects not detected by stereo depth → neural depth + occupancy fallback
- Strong backlighting washing out depth → HDR + exposure control
- Person moving faster than 2m/s → use conservative velocity assumption

### Unknown Unsafe Scenarios (must be validated)
- Reflective surfaces creating depth artifacts
- Multiple people occluding each other
- Objects misclassified as people (false positive → unnecessary stops, acceptable)
- People misclassified as objects (false negative → CRITICAL, must detect)

### Validation Approach
1. Isaac Sim digital twin testing (synthetic data + ground truth)
2. NvBlox reconstruction validation (compare to known scene geometry)
3. People detection evaluation (precision, recall, latency)
4. Full-loop E2E testing: human approach → detection → zone classification → speed reduction → stop

## Sources
- [NIST SSM Implementation](https://pmc.ncbi.nlm.nih.gov/articles/PMC5117641/)
- [ISO 10218 Overview](https://amdmachines.com/blog/robot-safety-standards-iso-10218-and-ts-15066-explained/)
- [SOTIF (ISO 21448)](https://visuresolutions.com/automotive/iso-21448/)
- [ISO/PAS 8800 for AI Safety](https://www.sgs.com/en/news/2025/04/safeguards-04625-introducing-iso-pas-8800-functional-safety-for-ai-in-road-vehicles)
- [Speed and Separation Monitoring Survey](https://www.preprints.org/manuscript/202502.1179)
