# cuRobo 0.7.7

## Critical Rules
1. **Input: Cartesian poses ONLY** - Never pre-solve IK
   - cuRobo does full trajectory optimization internally
   - Providing joint configurations as goals defeats the purpose
2. **Payload Configuration**: Must set in robot config
   - ee_mass: mass in kg
   - ee_com: center of mass [x, y, z] from end-effector
   - ee_inertia: 3x3 inertia tensor
3. **Singularity Avoidance**: Automatic
   - cuRobo trajectory optimization naturally avoids singularities
   - This is the key advantage over kinematic planners

## IK_FAIL Resolution
- Adjust seed configuration to current joint state
- Increase number of trajectory seeds
- Widen goal tolerance if precision allows
- Check if target is within workspace

## Container
- Image: isaac-lab-curobo:latest
- Built on Isaac Lab with cuRobo integration

## API Usage Pattern
```python
from curobo.wrap.reacher.motion_gen import MotionGen, MotionGenConfig

config = MotionGenConfig.load_from_robot_config(
    robot_cfg,
    world_cfg,
    tensor_args=tensor_args,
)
motion_gen = MotionGen(config)
motion_gen.warmup()

# Goal is always a Cartesian pose
result = motion_gen.plan_single(
    current_joint_state,  # current robot state
    goal_pose,            # target Cartesian pose (never joint config)
)
```
