# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Physics research skill for system identification and modeling."""
import os
import math
import logging

logger = logging.getLogger("skill.physics_research")
BASE_DIR = os.path.expanduser("~/agent-stack")


class PhysicsResearchSkill:
    """Identifies physical parameters from measurement data for sim-to-real transfer."""

    def identify_motor_parameters(self, voltage_data: list = None,
                                   current_data: list = None,
                                   velocity_data: list = None,
                                   torque_data: list = None,
                                   dt: float = 0.001) -> dict:
        """Identify DC motor parameters from measurement data.

        Uses least-squares fitting to identify:
        - Kt: torque constant (Nm/A)
        - Ke: back-EMF constant (V/(rad/s))
        - R: winding resistance (Ohm)
        - L: winding inductance (H)
        - J: rotor inertia (kg*m^2)
        - b: viscous friction (Nm/(rad/s))
        """
        voltage_data = voltage_data or []
        current_data = current_data or []
        velocity_data = velocity_data or []
        torque_data = torque_data or []

        n = min(len(voltage_data), len(current_data), len(velocity_data))
        if n < 5:
            logger.warning("Insufficient data for motor ID")
            return {"error": "Need at least 5 data points", "n_points": n}

        # Estimate Kt from torque and current: tau = Kt * i
        if torque_data:
            kt_estimates = []
            for tau, i in zip(torque_data[:n], current_data[:n]):
                if abs(i) > 0.01:
                    kt_estimates.append(tau / i)
            kt = sum(kt_estimates) / len(kt_estimates) if kt_estimates else 0.1
        else:
            kt = 0.1  # default

        # Estimate Ke from voltage and velocity: V = R*i + Ke*w
        # At steady state with known R, Ke = (V - R*i) / w
        # First estimate R from stall test (w=0): R = V/i
        stall_indices = [i for i, w in enumerate(velocity_data[:n]) if abs(w) < 0.01]
        if stall_indices:
            r_estimates = [
                voltage_data[i] / current_data[i]
                for i in stall_indices
                if abs(current_data[i]) > 0.01
            ]
            R = sum(r_estimates) / len(r_estimates) if r_estimates else 1.0
        else:
            R = 1.0

        # Ke from running data
        ke_estimates = []
        for idx in range(n):
            w = velocity_data[idx]
            v = voltage_data[idx]
            i = current_data[idx]
            if abs(w) > 0.1:
                ke = (v - R * i) / w
                if 0.001 < ke < 10.0:
                    ke_estimates.append(ke)
        ke = sum(ke_estimates) / len(ke_estimates) if ke_estimates else kt

        # Estimate inductance from transient response
        # di/dt = (V - R*i - Ke*w) / L
        if n > 2:
            di_dt_list = [(current_data[i + 1] - current_data[i]) / dt for i in range(n - 1)]
            L_estimates = []
            for idx in range(n - 1):
                di_dt = di_dt_list[idx]
                if abs(di_dt) > 0.1:
                    L_est = (voltage_data[idx] - R * current_data[idx]
                             - ke * velocity_data[idx]) / di_dt
                    if 0.0001 < abs(L_est) < 1.0:
                        L_estimates.append(abs(L_est))
            L = sum(L_estimates) / len(L_estimates) if L_estimates else 0.001
        else:
            L = 0.001

        # Estimate inertia and friction from deceleration
        # J * dw/dt = Kt * i - b * w
        if n > 2:
            dw_dt_list = [(velocity_data[i + 1] - velocity_data[i]) / dt for i in range(n - 1)]
            # Least squares: J * dw/dt + b * w = Kt * i
            sum_aa, sum_ab, sum_ba, sum_bb = 0.0, 0.0, 0.0, 0.0
            sum_ay, sum_by = 0.0, 0.0
            for idx in range(n - 1):
                a = dw_dt_list[idx]
                b_val = velocity_data[idx]
                y = kt * current_data[idx]
                sum_aa += a * a
                sum_ab += a * b_val
                sum_ba += b_val * a
                sum_bb += b_val * b_val
                sum_ay += a * y
                sum_by += b_val * y

            det = sum_aa * sum_bb - sum_ab * sum_ba
            if abs(det) > 1e-10:
                J = (sum_bb * sum_ay - sum_ab * sum_by) / det
                b = (sum_aa * sum_by - sum_ba * sum_ay) / det
                J = max(J, 1e-6)
                b = max(b, 0.0)
            else:
                J = 0.001
                b = 0.001
        else:
            J = 0.001
            b = 0.001

        result = {
            "Kt": kt,
            "Ke": ke,
            "R": R,
            "L": L,
            "J": J,
            "b": b,
            "n_points": n,
            "electrical_time_constant": L / R if R > 0 else 0.0,
            "mechanical_time_constant": J * R / (kt * ke) if kt * ke > 0 else 0.0,
        }
        logger.info(f"Motor ID: Kt={kt:.4f}, R={R:.4f}, J={J:.6f}")
        return result

    def identify_mass_properties(self, force_data: list = None,
                                  acceleration_data: list = None,
                                  position_data: list = None) -> dict:
        """Identify mass, center of mass, and inertia from force/motion data.

        Uses F = m*a and tau = I*alpha relationships.
        """
        force_data = force_data or []
        acceleration_data = acceleration_data or []

        n = min(len(force_data), len(acceleration_data))
        if n < 3:
            return {"error": "Need at least 3 data points", "n_points": n}

        # Estimate mass from F = m * a (linear case)
        mass_estimates = []
        for f, a in zip(force_data[:n], acceleration_data[:n]):
            if isinstance(f, (list, tuple)) and isinstance(a, (list, tuple)):
                f_mag = math.sqrt(sum(fi ** 2 for fi in f))
                a_mag = math.sqrt(sum(ai ** 2 for ai in a))
            else:
                f_mag = abs(f)
                a_mag = abs(a)
            if a_mag > 0.01:
                mass_estimates.append(f_mag / a_mag)

        mass = sum(mass_estimates) / len(mass_estimates) if mass_estimates else 1.0

        # Estimate center of mass from static balance data
        # For a body at rest, sum of moments about any point = 0
        # Using position_data as support points with known forces
        com = [0.0, 0.0, 0.0]
        if position_data and force_data:
            total_force = 0.0
            weighted_pos = [0.0, 0.0, 0.0]
            for pos, f in zip(position_data[:n], force_data[:n]):
                if isinstance(pos, (list, tuple)) and isinstance(f, (int, float)):
                    f_val = abs(f)
                    total_force += f_val
                    for dim in range(min(len(pos), 3)):
                        weighted_pos[dim] += f_val * pos[dim]
                elif isinstance(pos, (list, tuple)) and isinstance(f, (list, tuple)):
                    f_val = math.sqrt(sum(fi ** 2 for fi in f))
                    total_force += f_val
                    for dim in range(min(len(pos), 3)):
                        weighted_pos[dim] += f_val * pos[dim]

            if total_force > 0:
                com = [w / total_force for w in weighted_pos]

        # Rough inertia estimate: I ~ m * r^2
        # Using distance from COM to measurement points
        r_squared_avg = 0.0
        if position_data:
            r_sq_list = []
            for pos in position_data:
                if isinstance(pos, (list, tuple)):
                    r_sq = sum((p - c) ** 2 for p, c in zip(pos[:3], com))
                    r_sq_list.append(r_sq)
            r_squared_avg = sum(r_sq_list) / len(r_sq_list) if r_sq_list else 0.01

        inertia_estimate = mass * r_squared_avg

        result = {
            "mass": mass,
            "center_of_mass": com,
            "inertia_estimate": inertia_estimate,
            "mass_std": (math.sqrt(
                sum((m - mass) ** 2 for m in mass_estimates) / len(mass_estimates)
            ) if len(mass_estimates) > 1 else 0.0),
            "n_points": n,
        }
        logger.info(f"Mass ID: mass={mass:.3f}kg, COM={com}")
        return result

    def model_sensor_noise(self, samples: list, sensor_type: str = "generic") -> dict:
        """Model sensor noise characteristics from raw samples.

        Fits Gaussian noise model and estimates bias, white noise density,
        and random walk parameters.
        """
        if not samples:
            return {"error": "No samples provided"}

        # Flatten if multi-axis
        if isinstance(samples[0], (list, tuple)):
            n_axes = len(samples[0])
            per_axis = [[s[a] for s in samples] for a in range(n_axes)]
        else:
            n_axes = 1
            per_axis = [samples]

        axis_results = []
        for axis_idx, axis_data in enumerate(per_axis):
            n = len(axis_data)
            mean = sum(axis_data) / n
            variance = sum((x - mean) ** 2 for x in axis_data) / (n - 1) if n > 1 else 0.0
            std = math.sqrt(variance)

            # Bias: DC offset (mean of static data)
            bias = mean

            # White noise density (assuming known sample rate)
            # For accelerometer: units are m/s^2/sqrt(Hz)
            # For gyroscope: units are rad/s/sqrt(Hz)
            dt = 0.005  # assumed 200Hz
            noise_density = std * math.sqrt(dt)

            # Check for drift (random walk) by computing Allan variance at tau=1s
            tau = int(1.0 / dt)  # samples per second
            if n >= 2 * tau:
                averages = []
                for i in range(0, n - tau, tau):
                    avg = sum(axis_data[i:i + tau]) / tau
                    averages.append(avg)
                if len(averages) >= 2:
                    allan_diffs = [(averages[i + 1] - averages[i]) ** 2
                                   for i in range(len(averages) - 1)]
                    allan_var = sum(allan_diffs) / (2 * len(allan_diffs))
                    random_walk = math.sqrt(allan_var)
                else:
                    random_walk = 0.0
            else:
                random_walk = 0.0

            # Compute histogram bins for distribution analysis
            min_val = min(axis_data)
            max_val = max(axis_data)
            n_bins = min(50, max(10, n // 20))
            bin_width = (max_val - min_val) / n_bins if max_val > min_val else 1.0
            histogram = [0] * n_bins
            for x in axis_data:
                bin_idx = min(int((x - min_val) / bin_width), n_bins - 1)
                histogram[bin_idx] += 1

            axis_results.append({
                "axis": axis_idx,
                "mean": mean,
                "std": std,
                "variance": variance,
                "bias": bias,
                "noise_density": noise_density,
                "random_walk": random_walk,
                "min": min_val,
                "max": max_val,
                "peak_to_peak": max_val - min_val,
            })

        result = {
            "sensor_type": sensor_type,
            "n_samples": len(samples),
            "n_axes": n_axes,
            "per_axis": axis_results,
            "overall_noise_density": max(a["noise_density"] for a in axis_results),
        }
        logger.info(f"Noise model ({sensor_type}): {n_axes} axes, "
                     f"density={result['overall_noise_density']:.6f}")
        return result

    def analyze_sim_to_real_gap(self, sim_data: list, real_data: list,
                                 metric_name: str = "trajectory") -> dict:
        """Analyze discrepancy between simulation and real-world data.

        sim_data, real_data: lists of measurements to compare (same length ideally).
        Returns statistical analysis of the gap.
        """
        n = min(len(sim_data), len(real_data))
        if n == 0:
            return {"error": "No data to compare"}

        sim = sim_data[:n]
        real = real_data[:n]

        # Handle multi-dimensional data
        if isinstance(sim[0], (list, tuple)):
            dims = len(sim[0])
            errors = [math.sqrt(sum((s[d] - r[d]) ** 2 for d in range(dims)))
                      for s, r in zip(sim, real)]
            per_dim_bias = []
            for d in range(dims):
                dim_errors = [s[d] - r[d] for s, r in zip(sim, real)]
                bias = sum(dim_errors) / len(dim_errors)
                per_dim_bias.append(bias)
        else:
            errors = [abs(s - r) for s, r in zip(sim, real)]
            per_dim_bias = [sum(s - r for s, r in zip(sim, real)) / n]

        mean_error = sum(errors) / n
        max_error = max(errors)
        rms_error = math.sqrt(sum(e ** 2 for e in errors) / n)
        std_error = math.sqrt(sum((e - mean_error) ** 2 for e in errors) / n) if n > 1 else 0.0

        # Compute normalized error (relative to data range)
        if isinstance(real[0], (list, tuple)):
            all_vals = [v for point in real for v in point]
        else:
            all_vals = real
        data_range = max(all_vals) - min(all_vals) if all_vals else 1.0
        normalized_rms = rms_error / data_range if data_range > 0 else float("inf")

        # Gap quality assessment
        if normalized_rms < 0.01:
            quality = "excellent"
        elif normalized_rms < 0.05:
            quality = "good"
        elif normalized_rms < 0.10:
            quality = "acceptable"
        else:
            quality = "poor"

        result = {
            "metric": metric_name,
            "n_points": n,
            "mean_error": mean_error,
            "max_error": max_error,
            "rms_error": rms_error,
            "std_error": std_error,
            "normalized_rms": normalized_rms,
            "per_dim_bias": per_dim_bias,
            "quality": quality,
            "per_point_errors": errors,
        }
        logger.info(f"Sim-to-real gap ({metric_name}): {quality}, NRMS={normalized_rms:.4f}")
        return result

    def identify_friction(self, velocity_data: list, torque_data: list) -> dict:
        """Identify friction parameters from velocity-torque data.

        Fits Coulomb + viscous friction model: tau_f = mu_c * sign(v) + mu_v * v
        """
        n = min(len(velocity_data), len(torque_data))
        if n < 5:
            return {"error": "Need at least 5 data points"}

        vel = velocity_data[:n]
        tau = torque_data[:n]

        # Handle multi-joint data
        if isinstance(vel[0], (list, tuple)):
            n_joints = len(vel[0])
        else:
            n_joints = 1
            vel = [[v] for v in vel]
            tau = [[t] for t in tau]

        joint_friction = []
        for j in range(n_joints):
            v_j = [v[j] for v in vel]
            t_j = [t[j] for t in tau]

            # Separate positive and negative velocity regions
            pos_pairs = [(v, t) for v, t in zip(v_j, t_j) if v > 0.01]
            neg_pairs = [(v, t) for v, t in zip(v_j, t_j) if v < -0.01]

            # Least squares for tau = mu_c * sign(v) + mu_v * v
            # Rewrite as: tau = [sign(v), v] * [mu_c, mu_v]^T
            sum_s2, sum_sv, sum_v2 = 0.0, 0.0, 0.0
            sum_st, sum_vt = 0.0, 0.0
            for v, t in zip(v_j, t_j):
                if abs(v) < 0.001:
                    continue
                s = 1.0 if v > 0 else -1.0
                sum_s2 += s * s
                sum_sv += s * v
                sum_v2 += v * v
                sum_st += s * t
                sum_vt += v * t

            det = sum_s2 * sum_v2 - sum_sv * sum_sv
            if abs(det) > 1e-10:
                mu_c = (sum_v2 * sum_st - sum_sv * sum_vt) / det
                mu_v = (sum_s2 * sum_vt - sum_sv * sum_st) / det
            else:
                mu_c = 0.0
                mu_v = 0.0

            # Compute fit quality (R^2)
            predicted = [mu_c * (1.0 if v > 0 else -1.0) + mu_v * v
                         for v in v_j if abs(v) > 0.001]
            actual = [t for v, t in zip(v_j, t_j) if abs(v) > 0.001]
            if predicted and actual:
                mean_actual = sum(actual) / len(actual)
                ss_res = sum((a - p) ** 2 for a, p in zip(actual, predicted))
                ss_tot = sum((a - mean_actual) ** 2 for a in actual)
                r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            else:
                r_squared = 0.0

            joint_friction.append({
                "joint": j,
                "coulomb_friction": abs(mu_c),
                "viscous_friction": mu_v,
                "r_squared": r_squared,
                "n_positive": len(pos_pairs),
                "n_negative": len(neg_pairs),
            })

        result = {
            "model": "coulomb_viscous",
            "n_joints": n_joints,
            "n_points": n,
            "joints": joint_friction,
        }
        logger.info(f"Friction ID: {n_joints} joints identified")
        return result
