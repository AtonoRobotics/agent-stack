# Simulation Lessons Learned

## cuRobo vs Kinematic Planning
- cuRobo must receive Cartesian poses directly, never pre-solved joint configurations
- Kinematic planners (MoveIt, simple IK) fail at singularities
- cuRobo trajectory optimization handles singularities automatically
- Singularity demo: joint flip visible on "kinematic" (left) robot is the key demo for stakeholders

## Isaac Sim 5.1 Specifics
- physics_dt must be 1/240 for stable simulation
- Using 1/500 causes instability with articulated bodies
- Debug draw (isaacsim.util.debug_draw) is the only visualization method
- No OmniGraph plot nodes available

## Presentation Mode
- 50% slowdown required for stakeholder demos
- Manipulability index plot is the key "leave-behind" artifact
- Side-by-side comparison (cuRobo left, kinematic right) most impactful

## Payload Effects
- 5.3 kg camera payload significantly affects trajectory planning
- Must be configured in cuRobo as ee_mass, ee_com, ee_inertia
- Without payload config, torque limits are violated in real deployment
