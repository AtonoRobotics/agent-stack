# Isaac Sim 5.1.0

## Key Parameters
- Physics timestep: 1/240 seconds (NOT 1/500)
- Rendering: RTX path tracing or ray tracing
- Container: nvcr.io/nvidia/isaac-sim:5.1.0

## Debug Draw API
- Module: isaacsim.util.debug_draw
- No OmniGraph plot nodes available in 5.1
- Use debug_draw for trajectory visualization

## Common Issues and Fixes
1. **Black viewport**: Reset camera to default position
2. **PhysX cooking failed**: Rebuild collision meshes, check mesh normals
3. **High CPU usage**: Reduce physics substeps, simplify collision geometry
4. **Slow rendering**: Use ray tracing instead of path tracing for real-time

## Physics Configuration
```python
# Correct physics setup for Isaac Sim 5.1
physics_dt = 1.0 / 240.0  # 240 Hz physics
rendering_dt = 1.0 / 60.0  # 60 Hz rendering
gravity = (0.0, 0.0, -9.81)
```

## URDF Import
- Use isaacsim.asset.importer for URDF loading
- Set joint drive mode to "position" for robot arms
- Enable self-collision for accurate simulation
