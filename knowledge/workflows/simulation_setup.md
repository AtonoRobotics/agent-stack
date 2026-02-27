# Simulation Setup - Standing Rules

## STANDING RULE - SIMULATION PLATFORM

All simulations MUST run in Isaac Sim or Isaac Lab.
Never use PyBullet, Gazebo, MuJoCo, Webots or any other simulator.

### Isaac Sim
- Visual simulation, digital twin
- Physics simulation
- Sensor simulation
- Environment building
- Camera simulation

### Isaac Lab
- Reinforcement learning training
- GR00T data collection
- Policy evaluation
- Reward function testing

## Installation
- Location: check ~/workspaces/isaac_ros-dev/
- Container: nvcr.io/nvidia/isaac-sim:5.1.0
- ROS2 bridge: Isaac ROS 4.0

## Enforcement
Any agent generating simulation code that does not use Isaac Sim or Isaac Lab must be rejected and retried with explicit Isaac Sim instruction.
