# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Sensor testing skill for validating sensor accuracy and calibration."""
import os
import math
import logging

logger = logging.getLogger("skill.sensor_testing")
BASE_DIR = os.path.expanduser("~/agent-stack")


class SensorTestingSkill:
    """Tests and validates sensor calibration, noise, accuracy, and synchronization."""

    def test_camera_calibration(self, intrinsics: dict = None,
                                 measured_points: list = None,
                                 ground_truth_points: list = None) -> dict:
        """Test camera calibration by comparing projected vs measured points.

        intrinsics: {"fx": float, "fy": float, "cx": float, "cy": float,
                     "distortion": [k1, k2, p1, p2, k3]}
        measured_points: list of [u, v] pixel coordinates
        ground_truth_points: list of [x, y, z] world coordinates
        """
        intrinsics = intrinsics or {"fx": 600.0, "fy": 600.0, "cx": 320.0, "cy": 240.0,
                                     "distortion": [0.0, 0.0, 0.0, 0.0, 0.0]}
        measured_points = measured_points or []
        ground_truth_points = ground_truth_points or []

        fx, fy = intrinsics["fx"], intrinsics["fy"]
        cx, cy = intrinsics["cx"], intrinsics["cy"]

        reprojection_errors = []
        for (u_meas, v_meas), (x, y, z) in zip(measured_points, ground_truth_points):
            if z <= 0:
                continue
            # Project 3D point to pixel using pinhole model
            u_proj = fx * (x / z) + cx
            v_proj = fy * (y / z) + cy

            error = math.sqrt((u_proj - u_meas) ** 2 + (v_proj - v_meas) ** 2)
            reprojection_errors.append({
                "measured": [u_meas, v_meas],
                "projected": [u_proj, v_proj],
                "error_px": error,
            })

        if reprojection_errors:
            errors = [e["error_px"] for e in reprojection_errors]
            mean_error = sum(errors) / len(errors)
            max_error = max(errors)
            rms_error = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
        else:
            mean_error = max_error = rms_error = 0.0

        # Calibration quality thresholds
        quality = "excellent" if rms_error < 0.5 else (
            "good" if rms_error < 1.0 else (
                "acceptable" if rms_error < 2.0 else "poor"))

        passed = rms_error < 2.0

        result = {
            "test": "camera_calibration",
            "passed": passed,
            "mean_reprojection_error_px": mean_error,
            "max_reprojection_error_px": max_error,
            "rms_reprojection_error_px": rms_error,
            "num_points": len(reprojection_errors),
            "quality": quality,
            "intrinsics": intrinsics,
            "details": reprojection_errors[:20],
        }
        logger.info(f"Camera calibration test: {quality} (RMS={rms_error:.3f}px)")
        return result

    def test_imu_noise(self, samples: list = None, dt: float = 0.005) -> dict:
        """Test IMU noise characteristics from static samples.

        samples: list of {"linear_acceleration": [ax,ay,az], "angular_velocity": [wx,wy,wz]}
        dt: sample period in seconds
        """
        samples = samples or []
        if not samples:
            result = {
                "test": "imu_noise",
                "passed": False,
                "error": "No samples provided",
            }
            logger.warning("IMU noise test: no samples")
            return result

        # Extract accelerometer data
        accel_x = [s["linear_acceleration"][0] for s in samples]
        accel_y = [s["linear_acceleration"][1] for s in samples]
        accel_z = [s["linear_acceleration"][2] for s in samples]

        # Extract gyroscope data
        gyro_x = [s["angular_velocity"][0] for s in samples]
        gyro_y = [s["angular_velocity"][1] for s in samples]
        gyro_z = [s["angular_velocity"][2] for s in samples]

        def compute_noise_stats(values):
            n = len(values)
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
            std = math.sqrt(variance)
            peak_to_peak = max(values) - min(values)
            # Allan variance approximation (white noise)
            noise_density = std * math.sqrt(dt)
            return {
                "mean": mean,
                "std": std,
                "variance": variance,
                "peak_to_peak": peak_to_peak,
                "noise_density": noise_density,
            }

        accel_stats = {
            "x": compute_noise_stats(accel_x),
            "y": compute_noise_stats(accel_y),
            "z": compute_noise_stats(accel_z),
        }
        gyro_stats = {
            "x": compute_noise_stats(gyro_x),
            "y": compute_noise_stats(gyro_y),
            "z": compute_noise_stats(gyro_z),
        }

        # Check against typical IMU specs
        accel_noise_ok = all(
            accel_stats[axis]["noise_density"] < 0.005  # m/s^2/sqrt(Hz)
            for axis in ["x", "y", "z"]
        )
        gyro_noise_ok = all(
            gyro_stats[axis]["noise_density"] < 0.001  # rad/s/sqrt(Hz)
            for axis in ["x", "y", "z"]
        )

        # Check gravity reading (should be ~9.81 on z when static)
        gravity_error = abs(accel_stats["z"]["mean"] - 9.81)
        gravity_ok = gravity_error < 0.5

        passed = accel_noise_ok and gyro_noise_ok and gravity_ok

        result = {
            "test": "imu_noise",
            "passed": passed,
            "num_samples": len(samples),
            "sample_rate_hz": 1.0 / dt,
            "accelerometer": accel_stats,
            "gyroscope": gyro_stats,
            "gravity_error": gravity_error,
            "accel_noise_ok": accel_noise_ok,
            "gyro_noise_ok": gyro_noise_ok,
            "gravity_ok": gravity_ok,
        }
        logger.info(f"IMU noise test: {'PASS' if passed else 'FAIL'} "
                     f"(gravity_err={gravity_error:.3f})")
        return result

    def test_encoder_accuracy(self, commanded: list = None, measured: list = None,
                               resolution: float = 0.001) -> dict:
        """Test joint encoder accuracy against commanded positions.

        commanded: list of commanded joint angles [rad]
        measured: list of measured joint angles [rad]
        resolution: encoder resolution in radians
        """
        commanded = commanded or []
        measured = measured or []

        if len(commanded) != len(measured):
            min_len = min(len(commanded), len(measured))
            commanded = commanded[:min_len]
            measured = measured[:min_len]

        errors = [abs(c - m) for c, m in zip(commanded, measured)]
        quantization_errors = [abs(m - round(m / resolution) * resolution) for m in measured]

        if errors:
            mean_error = sum(errors) / len(errors)
            max_error = max(errors)
            rms_error = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
        else:
            mean_error = max_error = rms_error = 0.0

        if quantization_errors:
            mean_quant = sum(quantization_errors) / len(quantization_errors)
            max_quant = max(quantization_errors)
        else:
            mean_quant = max_quant = 0.0

        # Check linearity: compute correlation coefficient
        if len(commanded) > 2:
            n = len(commanded)
            mean_c = sum(commanded) / n
            mean_m = sum(measured) / n
            cov = sum((c - mean_c) * (m - mean_m) for c, m in zip(commanded, measured)) / n
            std_c = math.sqrt(sum((c - mean_c) ** 2 for c in commanded) / n)
            std_m = math.sqrt(sum((m - mean_m) ** 2 for m in measured) / n)
            correlation = cov / (std_c * std_m) if std_c > 0 and std_m > 0 else 0.0
        else:
            correlation = 1.0

        # Accuracy threshold: error should be within 2x encoder resolution
        accuracy_ok = max_error < 2.0 * resolution if errors else True
        linearity_ok = correlation > 0.9999

        passed = accuracy_ok and linearity_ok

        result = {
            "test": "encoder_accuracy",
            "passed": passed,
            "num_samples": len(errors),
            "mean_error_rad": mean_error,
            "max_error_rad": max_error,
            "rms_error_rad": rms_error,
            "mean_quantization_error": mean_quant,
            "max_quantization_error": max_quant,
            "linearity_correlation": correlation,
            "encoder_resolution": resolution,
            "accuracy_ok": accuracy_ok,
            "linearity_ok": linearity_ok,
        }
        logger.info(f"Encoder accuracy test: {'PASS' if passed else 'FAIL'} "
                     f"(max_err={max_error:.6f} rad)")
        return result

    def test_sensor_synchronization(self, sensor_timestamps: dict = None,
                                     max_skew_ms: float = 5.0) -> dict:
        """Test synchronization between multiple sensors.

        sensor_timestamps: {"camera": [t1,t2,...], "imu": [t1,t2,...], "encoder": [t1,t2,...]}
        max_skew_ms: maximum allowed time skew in milliseconds.
        """
        sensor_timestamps = sensor_timestamps or {}
        if len(sensor_timestamps) < 2:
            return {
                "test": "sensor_synchronization",
                "passed": False,
                "error": "Need at least 2 sensors to test synchronization",
            }

        sensor_names = list(sensor_timestamps.keys())
        pair_results = []

        for i in range(len(sensor_names)):
            for j in range(i + 1, len(sensor_names)):
                name_a = sensor_names[i]
                name_b = sensor_names[j]
                ts_a = sensor_timestamps[name_a]
                ts_b = sensor_timestamps[name_b]

                # Find closest timestamp pairs
                skews = []
                for t_a in ts_a:
                    if not ts_b:
                        continue
                    closest_b = min(ts_b, key=lambda t: abs(t - t_a))
                    skew_ms = abs(t_a - closest_b) * 1000.0
                    skews.append(skew_ms)

                if skews:
                    mean_skew = sum(skews) / len(skews)
                    max_skew = max(skews)
                    std_skew = math.sqrt(sum((s - mean_skew) ** 2 for s in skews) / len(skews))
                else:
                    mean_skew = max_skew = std_skew = 0.0

                pair_ok = max_skew <= max_skew_ms

                pair_results.append({
                    "sensor_a": name_a,
                    "sensor_b": name_b,
                    "mean_skew_ms": mean_skew,
                    "max_skew_ms": max_skew,
                    "std_skew_ms": std_skew,
                    "within_tolerance": pair_ok,
                    "num_comparisons": len(skews),
                })

        # Compute per-sensor jitter (inter-sample timing consistency)
        jitter_results = {}
        for name, timestamps in sensor_timestamps.items():
            if len(timestamps) < 2:
                jitter_results[name] = {"jitter_ms": 0.0, "nominal_period_ms": 0.0}
                continue
            intervals = [(timestamps[i + 1] - timestamps[i]) * 1000.0
                         for i in range(len(timestamps) - 1)]
            mean_interval = sum(intervals) / len(intervals)
            jitter = math.sqrt(
                sum((iv - mean_interval) ** 2 for iv in intervals) / len(intervals)
            )
            jitter_results[name] = {
                "nominal_period_ms": mean_interval,
                "jitter_ms": jitter,
                "max_interval_ms": max(intervals),
                "min_interval_ms": min(intervals),
            }

        all_pairs_ok = all(p["within_tolerance"] for p in pair_results)
        passed = all_pairs_ok

        result = {
            "test": "sensor_synchronization",
            "passed": passed,
            "max_allowed_skew_ms": max_skew_ms,
            "sensor_pairs": pair_results,
            "per_sensor_jitter": jitter_results,
            "all_within_tolerance": all_pairs_ok,
        }
        logger.info(f"Sync test: {'PASS' if passed else 'FAIL'} "
                     f"({len(pair_results)} pairs checked)")
        return result
