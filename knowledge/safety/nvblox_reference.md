# NvBlox — GPU-Accelerated 3D Reconstruction for Robot Safety

## Overview
NvBlox is NVIDIA's GPU-accelerated library for real-time 3D scene reconstruction using TSDF (Truncated Signed Distance Function) and ESDF (Euclidean Signed Distance Field) voxel grids. It processes depth camera and lidar data to produce 3D maps and 2D costmaps for robot safety and navigation.

**Our Docker images:** `isaac-ros-jazzy-4.2` and `isaac-ros-jazzy-zed` both include `ros-jazzy-isaac-ros-nvblox` and `ros-jazzy-nvblox-ros`.

## Architecture

### Voxel Layers
NvBlox maintains multiple aligned, co-located voxel grids:
- **TSDF Layer** — signed distance to nearest surface (truncated)
- **Color Layer** — RGB surface color from camera
- **Mesh Layer** — extracted triangle mesh (zero-level set of TSDF)
- **ESDF Layer** — full Euclidean distance field (non-truncated)
- **Occupancy Layer** — probabilistic occupancy (for dynamic objects)

### Mapping Modes
| Mode | Use Case | Key Feature |
|------|----------|-------------|
| `static_tsdf` | Static environments | Default, high-quality reconstruction |
| `static_occupancy` | Static with occupancy grid | Binary occupied/free |
| `human_with_static_tsdf` | Scenes with people | Separates humans into dedicated layer |
| `human_with_static_occupancy` | Scenes with people | Same but occupancy-based |
| `dynamic` | General dynamic objects | Uses Dynablox algorithm for freespace tracking |

### People Reconstruction (Safety-Critical)
- Uses semantic segmentation masks OR detection bounding boxes
- Humans are mapped into a separate occupancy layer
- Occupancy decays over time (voxels return to "unknown" when person leaves FOV)
- Subscriptions: mask image topic for people segmentation
- Node: `nvblox_human_node` (vs standard `nvblox_node`)

## Key ROS2 Parameters

### Voxel Configuration
| Parameter | Default | Description |
|-----------|---------|-------------|
| `voxel_size` | 0.050m | Cube dimension for 3D map |
| `mapping_type` | `static_tsdf` | Mapping mode selection |

### ESDF (Safety Distance Field)
| Parameter | Default | Description |
|-----------|---------|-------------|
| `esdf_integrator_max_distance_m` | 2.0m | Max computed distance |
| `esdf_slice_min_height` | — | Lower bound for 2D slice |
| `esdf_slice_max_height` | — | Upper bound for 2D slice |

### Occupancy Detection
| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_tsdf_distance_for_occupancy_m` | 0.150m | Occupied/free threshold |
| `occupied_region_half_width_m` | 0.100m | Obstacle expansion radius |

### Update Rates
| Parameter | Default | Description |
|-----------|---------|-------------|
| `integrate_depth_rate_hz` | 40Hz | Depth integration rate |
| `integrate_lidar_rate_hz` | 40Hz | Lidar integration rate |
| `update_esdf_rate_hz` | 5Hz | ESDF recomputation rate |
| `decay_dynamic_occupancy_rate_hz` | 10Hz | Dynamic object decay rate |

### Map Management
| Parameter | Default | Description |
|-----------|---------|-------------|
| `map_clearing_radius_m` | 5.0m | Radius for map cleanup |
| `clear_map_outside_radius_rate_hz` | 1.0Hz | Cleanup frequency |
| `projective_integrator_max_integration_distance_m` | 7.0m | Max depth range |

## Performance (per voxel_size=0.05m)
| Operation | Jetson Orin | x86+Ampere |
|-----------|-------------|------------|
| TSDF integration | 0.1–2.1ms | <1ms |
| Meshing | 0.3–13ms | <5ms |
| ESDF calculation | 0.3–6.2ms | <3ms |
| Dynamics | 0.4–2.0ms | <1ms |

## Safety Application: Distance Field for Zone Monitoring
The ESDF provides the **minimum distance from any point in space to the nearest obstacle/person**. For our safety system:
1. NvBlox publishes ESDF voxel grid
2. Safety node queries ESDF at robot link positions
3. Minimum distance to nearest human/obstacle determines safety zone
4. Zone classification drives speed limiting or E-stop

## Sensor Requirements
- Minimum imager framerate: 30Hz
- Maximum permissible jitter: ±2ms
- Supported: depth cameras (RealSense, ZED), 3D LiDAR
- Camera must provide: depth image + camera intrinsics + camera pose (from VSLAM or other)

## Sources
- [NvBlox Technical Details](https://nvidia-isaac-ros.github.io/concepts/scene_reconstruction/nvblox/technical_details.html)
- [Isaac ROS NvBlox](https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_nvblox/index.html)
- [NvBlox Parameters](https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_nvblox/isaac_ros_nvblox/api/parameters.html)
- [GitHub: nvidia-isaac/nvblox](https://github.com/nvidia-isaac/nvblox)
