# NVIDIA Halos — Safety System for Robots and Autonomous Vehicles

## Overview
NVIDIA Halos is a full-stack safety system originally designed for autonomous vehicles, now expanded to industrial robotics. It provides "outside-in" safety monitoring using infrastructure-mounted sensors and AI-powered safety agents.

## Architecture

### Three-Computer Design (AV Origin)
| Computer | Role |
|----------|------|
| **DGX** | AI model training |
| **Omniverse + Cosmos** | Simulation and digital twin validation |
| **AGX/IGX** | Edge deployment and real-time inference |

### Robot Safety: Outside-In Approach
Unlike traditional onboard-only safety (inside-out), Halos uses **infrastructure-mounted cameras** to provide:
- 360° situational awareness (eliminates blind spots)
- Multi-robot fleet supervision from a single system
- Environmental context that onboard sensors miss

### Key Components
1. **NVIDIA IGX Thor** — Industrial-grade edge AI compute platform
   - Real-time multimodal sensor fusion
   - Functional safety hardware support
   - Enterprise security + industrial reliability

2. **Safety AI Agents** — Continuous monitoring with adaptive reasoning
   - Fuse low-latency detections with safety monitoring logic
   - Supervise multiple robots simultaneously
   - Autonomous decision-making: slow, stop, or allow full speed

3. **Holoscan Sensor Bridge** — Unified sensor-to-compute architecture
   - Built-in AI safety
   - Multi-camera fusion

4. **NVIDIA Metropolis Blueprint** — Video search and event summarization
5. **NVIDIA Cosmos Reason** — Vision-language model for operational reasoning

## Safety Functions

### Speed and Separation Monitoring (SSM)
- Full speed when zones are clear of people
- Automatic slowdown when workers approach
- Immediate stop when workers enter protected area
- Applies to: AMRs, robot arms, entire fleets

### Zone-Based Safety
- Virtual tripwires for zone transitions
- Dynamic zones that adapt to operational context
- Handles blind corners, high-rack areas, intersections
- Multiple robots supervised simultaneously

### Compliance
- **TÜV Rheinland** inspection and accreditation
- NVIDIA Halos AI Systems Inspection Lab (ANAB accredited)
- Aligned with: ISO 13849, IEC 62443, ISO 10218
- Safety extension packages for IGX platform

## Relevance to Our System
Halos represents the **gold standard** for NVIDIA robot safety but requires:
- NVIDIA IGX Thor hardware (~$15,000+)
- Infrastructure-mounted cameras (not just onboard)
- TÜV certification process

**For our CR10 system**, we take the same architectural principles but implement at a smaller scale:
- ZED-X cameras (onboard + potentially infrastructure-mounted)
- NvBlox for 3D reconstruction (already in our Docker)
- Custom safety node implementing SSM concepts
- No TÜV certification needed for dev/demo phase

## Sources
- [NVIDIA Halos for Industrial Robots](https://www.nvidia.com/en-us/use-cases/functional-safety-ai-agents-industrial-robots/)
- [NVIDIA Halos Blog](https://blogs.nvidia.com/blog/halos-safety-system-autonomous-vehicles/)
- [European Robot Makers + Halos](https://blogs.nvidia.com/blog/european-robot-makers-isaac-omniverse-halos-safe-physical-ai/)
- [NVIDIA IGX Platform](https://www.nvidia.com/en-us/edge-computing/products/igx/)
