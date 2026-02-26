# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Controller design skill for robot joint and task-space control."""
import os
import math
import logging

logger = logging.getLogger("skill.controller_design")
BASE_DIR = os.path.expanduser("~/agent-stack")


class ControllerDesignSkill:
    """Designs and tunes PID and impedance controllers for robot joints."""

    def design_pid(self, plant: dict = None, requirements: dict = None) -> dict:
        """Design PID controller gains using Ziegler-Nichols or specified method.

        plant: {"Ku": float (ultimate gain), "Tu": float (ultimate period),
                "type": "position"|"velocity", "inertia": float, "damping": float}
        requirements: {"settling_time": float, "overshoot_pct": float, "method": str}
        """
        plant = plant or {}
        requirements = requirements or {}

        method = requirements.get("method", "ziegler_nichols")
        plant_type = plant.get("type", "position")

        if method == "ziegler_nichols":
            Ku = plant.get("Ku", 10.0)
            Tu = plant.get("Tu", 0.5)

            # Ziegler-Nichols PID tuning rules
            Kp = 0.6 * Ku
            Ki = 2.0 * Kp / Tu
            Kd = Kp * Tu / 8.0

        elif method == "cohen_coon":
            # Cohen-Coon method for FOPDT model
            K = plant.get("gain", 1.0)
            tau = plant.get("time_constant", 0.5)
            theta = plant.get("dead_time", 0.05)
            r = theta / tau

            Kp = (1.0 / (K * r)) * (1.35 + 0.25 * r)
            Ti = theta * (2.5 - 2.0 * r) / (1.0 - 0.39 * r)
            Td = 0.37 * theta / (1.0 - 0.81 * r)
            Ki = Kp / Ti
            Kd = Kp * Td

        elif method == "pole_placement":
            # Pole placement for second-order system
            inertia = plant.get("inertia", 0.1)
            damping = plant.get("damping", 0.01)
            settling_time = requirements.get("settling_time", 0.5)
            overshoot_pct = requirements.get("overshoot_pct", 5.0)

            # Desired closed-loop poles
            zeta = -math.log(overshoot_pct / 100.0) / math.sqrt(
                math.pi ** 2 + math.log(overshoot_pct / 100.0) ** 2
            ) if overshoot_pct > 0 else 1.0
            wn = 4.0 / (zeta * settling_time)

            # PD gains from desired dynamics: m*a + (b+Kd)*v + Kp*e = 0
            Kp = inertia * wn ** 2
            Kd = 2.0 * zeta * wn * inertia - damping
            Ki = Kp * 0.1  # small integral to eliminate steady-state error

        else:
            Kp, Ki, Kd = 10.0, 1.0, 0.5

        # Anti-windup limit
        max_integral = plant.get("max_torque", 50.0) / max(Ki, 0.001)

        # Compute expected performance metrics
        if method == "pole_placement":
            wn_actual = math.sqrt(Kp / plant.get("inertia", 0.1))
            zeta_actual = (plant.get("damping", 0.01) + Kd) / (
                2.0 * math.sqrt(plant.get("inertia", 0.1) * Kp))
        else:
            wn_actual = math.sqrt(Kp)
            zeta_actual = Kd / (2.0 * math.sqrt(Kp)) if Kp > 0 else 0.0

        expected_settling = 4.0 / (zeta_actual * wn_actual) if zeta_actual * wn_actual > 0 else float("inf")
        expected_overshoot = 100.0 * math.exp(
            -zeta_actual * math.pi / math.sqrt(1 - zeta_actual ** 2)
        ) if 0 < zeta_actual < 1 else 0.0

        result = {
            "gains": {"Kp": Kp, "Ki": Ki, "Kd": Kd},
            "method": method,
            "plant_type": plant_type,
            "anti_windup_limit": max_integral,
            "expected_performance": {
                "natural_frequency_hz": wn_actual / (2.0 * math.pi),
                "damping_ratio": zeta_actual,
                "settling_time_s": expected_settling,
                "overshoot_pct": expected_overshoot,
            },
        }
        logger.info(f"PID designed ({method}): Kp={Kp:.3f}, Ki={Ki:.3f}, Kd={Kd:.3f}")
        return result

    def tune_pid(self, current_gains: dict, step_response: list,
                 target_settling: float = 0.5, target_overshoot: float = 5.0) -> dict:
        """Tune existing PID gains based on step response data.

        current_gains: {"Kp": float, "Ki": float, "Kd": float}
        step_response: list of {"time": float, "value": float, "setpoint": float}
        """
        if not step_response:
            return {"error": "No step response data provided"}

        Kp = current_gains.get("Kp", 1.0)
        Ki = current_gains.get("Ki", 0.0)
        Kd = current_gains.get("Kd", 0.0)

        times = [s["time"] for s in step_response]
        values = [s["value"] for s in step_response]
        setpoint = step_response[0].get("setpoint", values[-1])

        # Measure actual performance
        final_value = sum(values[-5:]) / min(5, len(values))
        steady_state_error = abs(setpoint - final_value)

        # Find overshoot
        if setpoint > values[0]:
            peak = max(values)
            overshoot_pct = 100.0 * (peak - setpoint) / (setpoint - values[0]) if setpoint != values[0] else 0.0
        else:
            peak = min(values)
            overshoot_pct = 100.0 * (setpoint - peak) / (values[0] - setpoint) if setpoint != values[0] else 0.0

        # Find settling time (2% band)
        band = 0.02 * abs(setpoint - values[0]) if setpoint != values[0] else 0.02
        settling_time = times[-1]
        for i in range(len(values) - 1, -1, -1):
            if abs(values[i] - setpoint) > band:
                settling_time = times[min(i + 1, len(times) - 1)]
                break

        # Find rise time (10% to 90%)
        target_10 = values[0] + 0.1 * (setpoint - values[0])
        target_90 = values[0] + 0.9 * (setpoint - values[0])
        t_10, t_90 = times[0], times[-1]
        for t, v in zip(times, values):
            if (setpoint > values[0] and v >= target_10) or (setpoint < values[0] and v <= target_10):
                t_10 = t
                break
        for t, v in zip(times, values):
            if (setpoint > values[0] and v >= target_90) or (setpoint < values[0] and v <= target_90):
                t_90 = t
                break
        rise_time = t_90 - t_10

        # Tuning adjustments
        new_Kp = Kp
        new_Ki = Ki
        new_Kd = Kd

        # If overshoot too high, increase Kd and decrease Kp
        if overshoot_pct > target_overshoot * 1.2:
            new_Kd *= 1.3
            new_Kp *= 0.9

        # If overshoot too low and settling too slow, increase Kp
        if overshoot_pct < target_overshoot * 0.5 and settling_time > target_settling * 1.2:
            new_Kp *= 1.2

        # If settling time too long, increase Kp moderately
        if settling_time > target_settling * 1.5:
            new_Kp *= 1.1
            new_Kd *= 1.1

        # If steady-state error, increase Ki
        if steady_state_error > 0.01:
            new_Ki *= 1.5 if new_Ki > 0 else 0.1

        result = {
            "current_gains": current_gains,
            "tuned_gains": {"Kp": new_Kp, "Ki": new_Ki, "Kd": new_Kd},
            "measured_performance": {
                "overshoot_pct": overshoot_pct,
                "settling_time_s": settling_time,
                "rise_time_s": rise_time,
                "steady_state_error": steady_state_error,
                "peak_value": peak,
            },
            "targets": {
                "settling_time_s": target_settling,
                "overshoot_pct": target_overshoot,
            },
            "adjustments_made": {
                "Kp_change_pct": 100.0 * (new_Kp - Kp) / Kp if Kp > 0 else 0.0,
                "Ki_change_pct": 100.0 * (new_Ki - Ki) / Ki if Ki > 0 else 0.0,
                "Kd_change_pct": 100.0 * (new_Kd - Kd) / Kd if Kd > 0 else 0.0,
            },
        }
        logger.info(f"PID tuned: Kp {Kp:.3f}->{new_Kp:.3f}, overshoot {overshoot_pct:.1f}%")
        return result

    def design_impedance_controller(self, desired_stiffness: list = None,
                                     desired_damping: list = None,
                                     desired_inertia: list = None,
                                     task_space: bool = True) -> dict:
        """Design impedance controller for compliant robot behavior.

        Impedance model: M_d * x_dd + D_d * x_d + K_d * (x - x_0) = F_ext
        """
        n_dof = 6 if task_space else 7  # Cartesian or joint space
        desired_stiffness = desired_stiffness or [500.0] * n_dof
        desired_damping = desired_damping or [None] * n_dof
        desired_inertia = desired_inertia or [1.0] * n_dof

        # Compute critical damping if not specified
        for i in range(n_dof):
            if desired_damping[i] is None:
                desired_damping[i] = 2.0 * math.sqrt(
                    desired_stiffness[i] * desired_inertia[i]
                )

        # Compute damping ratios
        damping_ratios = [
            d / (2.0 * math.sqrt(k * m)) if k * m > 0 else 0.0
            for d, k, m in zip(desired_damping, desired_stiffness, desired_inertia)
        ]

        # Natural frequencies
        natural_freqs = [
            math.sqrt(k / m) / (2.0 * math.pi) if m > 0 else 0.0
            for k, m in zip(desired_stiffness, desired_inertia)
        ]

        axis_labels = ["x", "y", "z", "rx", "ry", "rz"] if task_space else [
            f"q{i}" for i in range(n_dof)
        ]

        code = f'''import numpy as np

class ImpedanceController:
    def __init__(self):
        self.M_d = np.diag({desired_inertia})  # Desired inertia
        self.D_d = np.diag({desired_damping})  # Desired damping
        self.K_d = np.diag({desired_stiffness})  # Desired stiffness
        self.x_d = np.zeros({n_dof})  # Desired position (equilibrium)
        self.task_space = {task_space}

    def compute(self, x, x_dot, x_ddot_ref, f_ext, J=None, M=None):
        """Compute torque command from impedance law.

        tau = J^T * (M_d * x_ddot_ref + D_d * (x_dot_d - x_dot) + K_d * (x_d - x) + f_ext)
        If task_space, transforms to joint torques via Jacobian.
        """
        e = self.x_d - x
        e_dot = -x_dot  # assuming x_dot_d = 0

        # Impedance force
        f_imp = self.M_d @ x_ddot_ref + self.D_d @ e_dot + self.K_d @ e

        if self.task_space and J is not None:
            # Transform to joint torques
            tau = J.T @ f_imp
        else:
            tau = f_imp

        return tau

    def set_equilibrium(self, x_d):
        self.x_d = np.array(x_d)

controller = ImpedanceController()
'''
        result = {
            "code": code,
            "parameters": {
                "stiffness": dict(zip(axis_labels, desired_stiffness)),
                "damping": dict(zip(axis_labels, desired_damping)),
                "inertia": dict(zip(axis_labels, desired_inertia)),
                "damping_ratios": dict(zip(axis_labels, damping_ratios)),
                "natural_frequencies_hz": dict(zip(axis_labels, natural_freqs)),
            },
            "task_space": task_space,
            "n_dof": n_dof,
        }
        logger.info(f"Impedance controller designed: {'task' if task_space else 'joint'} space, "
                     f"K={desired_stiffness}")
        return result

    def validate_stability(self, controller_gains: dict, plant: dict) -> dict:
        """Validate closed-loop stability using gain/phase margin analysis.

        controller_gains: {"Kp": float, "Ki": float, "Kd": float}
        plant: {"inertia": float, "damping": float, "poles": [float,...]}
        """
        Kp = controller_gains.get("Kp", 1.0)
        Ki = controller_gains.get("Ki", 0.0)
        Kd = controller_gains.get("Kd", 0.0)
        inertia = plant.get("inertia", 0.1)
        damping = plant.get("damping", 0.01)

        # Closed-loop characteristic equation: J*s^2 + (b+Kd)*s + Kp + Ki/s = 0
        # => J*s^3 + (b+Kd)*s^2 + Kp*s + Ki = 0
        a3 = inertia
        a2 = damping + Kd
        a1 = Kp
        a0 = Ki

        # Routh-Hurwitz stability criterion
        # For 3rd order: all coefficients positive AND a2*a1 > a3*a0
        all_positive = a3 > 0 and a2 > 0 and a1 > 0 and a0 >= 0
        routh_criterion = a2 * a1 > a3 * a0 if a0 > 0 else True

        stable = all_positive and routh_criterion

        # Approximate gain margin using crossover frequency
        # Open-loop: G(s) = (Kd*s^2 + Kp*s + Ki) / (J*s^3 + b*s^2)
        # At phase crossover (phase = -180), compute gain
        # Simplified: gain margin ~ Kp / (inertia * wn^2) for dominant poles
        wn = math.sqrt(Kp / inertia) if inertia > 0 else 1.0
        zeta = (damping + Kd) / (2.0 * math.sqrt(inertia * Kp)) if inertia * Kp > 0 else 0.0

        # Gain margin approximation
        if zeta > 0:
            gain_margin_db = 20.0 * math.log10(2.0 * zeta) if zeta > 0.01 else -40.0
        else:
            gain_margin_db = -float("inf")

        # Phase margin approximation
        phase_margin_deg = math.degrees(math.atan2(2.0 * zeta, 1.0)) if zeta > 0 else 0.0
        # More accurate: PM ~ atan(2*zeta / sqrt(sqrt(1+4*zeta^4) - 2*zeta^2))
        discriminant = math.sqrt(1 + 4 * zeta ** 4) - 2 * zeta ** 2
        if discriminant > 0:
            wpc = wn * math.sqrt(discriminant)
            phase_margin_deg = math.degrees(
                math.atan2(2.0 * zeta * wpc / wn, 1.0 - (wpc / wn) ** 2)
            )

        result = {
            "stable": stable,
            "routh_hurwitz": {
                "all_positive": all_positive,
                "criterion_met": routh_criterion,
                "coefficients": [a3, a2, a1, a0],
            },
            "margins": {
                "gain_margin_db": gain_margin_db,
                "phase_margin_deg": phase_margin_deg,
                "gain_margin_ok": gain_margin_db > 6.0,
                "phase_margin_ok": phase_margin_deg > 30.0,
            },
            "closed_loop": {
                "natural_frequency_hz": wn / (2.0 * math.pi),
                "damping_ratio": zeta,
                "bandwidth_hz": wn * math.sqrt(1 - 2 * zeta ** 2 +
                                                 math.sqrt(2 - 4 * zeta ** 2 + 4 * zeta ** 4))
                                / (2.0 * math.pi) if zeta < 0.707 else wn / (2.0 * math.pi),
            },
        }
        logger.info(f"Stability: {'STABLE' if stable else 'UNSTABLE'}, "
                     f"GM={gain_margin_db:.1f}dB, PM={phase_margin_deg:.1f}deg")
        return result

    def test_performance(self, controller_gains: dict, plant: dict,
                          test_duration: float = 2.0, dt: float = 0.001) -> dict:
        """Simulate step response to test controller performance.

        Returns simulated time-domain response.
        """
        Kp = controller_gains.get("Kp", 1.0)
        Ki = controller_gains.get("Ki", 0.0)
        Kd = controller_gains.get("Kd", 0.0)
        inertia = plant.get("inertia", 0.1)
        damping_coeff = plant.get("damping", 0.01)
        max_torque = plant.get("max_torque", 50.0)

        setpoint = 1.0  # unit step
        n_steps = int(test_duration / dt)

        # State: [position, velocity]
        pos = 0.0
        vel = 0.0
        integral = 0.0

        response = []
        for i in range(n_steps):
            t = i * dt
            error = setpoint - pos
            integral += error * dt
            # Anti-windup
            integral = max(-max_torque / max(Ki, 0.001),
                          min(max_torque / max(Ki, 0.001), integral))
            derivative = -vel  # d/dt of error when setpoint is constant

            # PID output
            tau = Kp * error + Ki * integral + Kd * derivative
            tau = max(-max_torque, min(max_torque, tau))  # saturate

            # Plant dynamics: J * a + b * v = tau
            acc = (tau - damping_coeff * vel) / inertia
            vel += acc * dt
            pos += vel * dt

            if i % max(1, n_steps // 200) == 0:
                response.append({"time": t, "position": pos, "velocity": vel,
                                  "torque": tau, "error": error})

        # Extract metrics from response
        final_pos = response[-1]["position"]
        steady_state_error = abs(setpoint - final_pos)

        positions = [r["position"] for r in response]
        peak = max(positions)
        overshoot = 100.0 * (peak - setpoint) / setpoint if setpoint != 0 else 0.0

        # Settling time (2% band)
        band = 0.02 * setpoint
        settling_idx = len(response) - 1
        for i in range(len(response) - 1, -1, -1):
            if abs(response[i]["position"] - setpoint) > band:
                settling_idx = min(i + 1, len(response) - 1)
                break
        settling_time = response[settling_idx]["time"]

        max_torque_used = max(abs(r["torque"]) for r in response)

        result = {
            "response": response,
            "metrics": {
                "overshoot_pct": overshoot,
                "settling_time_s": settling_time,
                "steady_state_error": steady_state_error,
                "peak_value": peak,
                "max_torque_used": max_torque_used,
                "torque_saturation": max_torque_used >= max_torque * 0.99,
            },
            "simulation": {
                "duration_s": test_duration,
                "dt": dt,
                "n_steps": n_steps,
                "setpoint": setpoint,
            },
        }
        logger.info(f"Performance test: OS={overshoot:.1f}%, Ts={settling_time:.3f}s")
        return result
