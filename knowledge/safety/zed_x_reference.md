# Stereolabs ZED-X — Industrial Stereo Camera for Robot Safety

## Overview
The ZED-X is an IP67-rated industrial stereo camera with neural depth sensing, designed for robotics and autonomous systems. It connects via GMSL2 to NVIDIA Jetson/IGX platforms.

**Our Docker:** `isaac-ros-jazzy-zed` includes ZED SDK 5.2 with full ROS2 integration.

## Key Specifications

### Imaging
| Spec | Value |
|------|-------|
| Sensor | Dual 2.3MP, 3µm pixel, global shutter |
| Resolution | 1920×1200 @ 60fps, 960×600 @ 120fps |
| Format | 16:10 native |
| HDR | Yes |

### Depth Sensing
| Spec | 2.2mm Lens | 4mm Lens |
|------|-----------|----------|
| Range | 0.3–20m | 1.0–35m |
| Ideal Range | 0.3–12m | 1.0–20m |
| Technology | Neural Depth Engine 2 |
| Max FPS | 120Hz |

### Field of View
| Spec | 2.2mm Lens | 4mm Lens |
|------|-----------|----------|
| Horizontal | 110° | 80° |
| Vertical | 80° | 52° |
| Diagonal | 120° | 91° |

### IMU
| Spec | Value |
|------|-------|
| Accelerometer | 16-bit, ±12g |
| Gyroscope | 16-bit, ±1000°/s |
| Data Rate | 400Hz |
| Pose Update | Up to 120Hz |
| Pose Drift | 0.3% translation, 0.003°/m rotation |

### Physical
| Spec | Value |
|------|-------|
| Dimensions | 164 × 32 × 37mm |
| Weight | 240g |
| Enclosure | Aluminum, IP67 |
| Temperature | -20°C to +55°C |
| Baseline | 120mm |
| Connectivity | GMSL2 (FAKRA Z), up to 15m cable |
| Power | PoC via GMSL2 |
| Mounting | 1/4"-20 UNC + M4 threads |

## Safety-Relevant Capabilities

### For NvBlox Integration
- Depth at 30Hz+ (meets NvBlox minimum requirement)
- 0.3m minimum range (close-proximity detection)
- Neural depth fills holes that stereo matching misses
- Global shutter eliminates motion blur (critical for safety)

### For People Detection
- ZED SDK body tracking (skeleton detection)
- Depth + RGB for semantic segmentation input to NvBlox human mode
- 120° diagonal FOV covers wide workspace area

### Limitations for Safety
- **NOT safety-rated** (no SIL/PL certification)
- Stereo depth degrades on: textureless surfaces, strong backlighting, transparent objects
- Neural depth can hallucinate in edge cases (SOTIF concern)
- Single camera = single point of failure (redundancy needed for safety)

## ROS2 Topics (ZED SDK)
| Topic | Type | Description |
|-------|------|-------------|
| `/zed/depth/depth_registered` | Image | Depth image aligned to RGB |
| `/zed/rgb/image_rect_color` | Image | Rectified color image |
| `/zed/point_cloud/cloud_registered` | PointCloud2 | 3D point cloud |
| `/zed/body_trk/skeletons` | Custom | Detected human skeletons |
| `/zed/imu/data` | Imu | IMU measurements |
| `/zed/pose` | PoseStamped | Camera pose from visual odometry |

## Sources
- [ZED-X Product Page](https://www.stereolabs.com/products/zed-x)
- [ZED-X Specifications](https://www.stereolabs.com/docs/cameras/zed-x)
- [ZED-X Launch Article](https://www.therobotreport.com/stereolabs-zed-x-camera/)
