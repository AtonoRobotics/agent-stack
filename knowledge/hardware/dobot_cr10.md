# Dobot CR10

## Specifications
- Type: 6-DOF collaborative robot arm
- Payload: 10 kg max
- Reach: 1300 mm
- Repeatability: +/-0.03 mm
- Weight: 33.5 kg
- IP Rating: IP54

## Joint Limits (from URDF)
| Joint | Min (deg) | Max (deg) | Max Velocity (deg/s) |
|-------|-----------|-----------|---------------------|
| J1    | -360      | 360       | 180                 |
| J2    | -160      | 160       | 180                 |
| J3    | -160      | 160       | 180                 |
| J4    | -360      | 360       | 250                 |
| J5    | -360      | 360       | 250                 |
| J6    | -360      | 360       | 250                 |

## Current Configuration
- End Effector: Camera mount (custom)
- Payload: ARRI Alexa Mini + Zeiss 35mm + FIZ
- Total Payload Mass: 5.3 kg
- Center of Mass Offset: [0, 0, 0.12] m from flange

## Camera Mount
- Custom aluminum bracket
- Quick-release plate compatible
- Cable routing through arm channels
- FIZ motor mount integrated

## FIZ System
- Controller: Preston MDR4
- Motors: Preston DM2 (Focus, Iris, Zoom)
- Wireless: Preston Light Ranger 2
- Integration: RS-422 serial via USB adapter

## Known Issues
1. **Wrist Singularity**: J4/J5 alignment at ~0deg causes IK failures
   - Solution: cuRobo handles automatically with trajectory optimization
   - Previous kinematic planners failed here consistently
2. **J2/J3 Coupling**: Near full extension, torque limits can be exceeded
   - Monitor manipulability index near workspace boundaries
3. **Cable Management**: Camera cables can snag at J4 rotation
   - Maximum J4 rotation with cables: +/-270deg

## Known IK_FAIL Cases
- Straight-arm extension (J2=0, J3=0) with wrist rotation
- Positions directly above base (singularity zone)
- Near-boundary reach at >1250mm from base
