# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Isaac Lab RL training skill."""
import os
import json
import logging

logger = logging.getLogger("skill.isaac_lab")
BASE_DIR = os.path.expanduser("~/agent-stack")


class IsaacLabSkill:
    """Manages RL environment setup, training, and evaluation in Isaac Lab."""

    def setup_rl_environment(self, env_config: dict = None) -> dict:
        """Generate Isaac Lab RL environment setup code.

        env_config: {"task": str, "num_envs": int, "device": str,
                     "observation_space": dict, "action_space": dict}
        """
        env_config = env_config or {
            "task": "Isaac-Reach-Franka-v0",
            "num_envs": 4096,
            "device": "cuda:0",
            "sim_dt": 1.0 / 120.0,
            "control_dt": 1.0 / 30.0,
            "episode_length_s": 5.0,
        }

        code = f'''import torch
from omni.isaac.lab.envs import ManagerBasedRLEnv, ManagerBasedRLEnvCfg
from omni.isaac.lab.scene import InteractiveSceneCfg
from omni.isaac.lab.utils import configclass

@configclass
class TaskEnvCfg(ManagerBasedRLEnvCfg):
    """Configuration for the RL environment."""

    # Scene
    scene: InteractiveSceneCfg = InteractiveSceneCfg(
        num_envs={env_config["num_envs"]},
        env_spacing=2.5,
    )

    # Simulation
    sim_dt = {env_config.get("sim_dt", 1.0/120.0)}
    decimation = int({env_config.get("control_dt", 1.0/30.0)} / {env_config.get("sim_dt", 1.0/120.0)})
    episode_length_s = {env_config.get("episode_length_s", 5.0)}

    # Observation and action spaces configured via managers
    observations = ObservationsCfg()
    actions = ActionsCfg()
    rewards = RewardsCfg()
    terminations = TerminationsCfg()

# Create environment
env_cfg = TaskEnvCfg()
env_cfg.scene.num_envs = {env_config["num_envs"]}
env = ManagerBasedRLEnv(cfg=env_cfg)

print(f"RL Environment created:")
print(f"  Task: {env_config['task']}")
print(f"  Num envs: {{env.num_envs}}")
print(f"  Obs shape: {{env.observation_space.shape}}")
print(f"  Act shape: {{env.action_space.shape}}")
print(f"  Device: {{env.device}}")
'''
        logger.info(f"Setup RL env: {env_config['task']}, {env_config['num_envs']} envs")
        return {"code": code, "env_config": env_config}

    def design_reward_function(self, task_type: str = "reach",
                                reward_components: dict = None) -> dict:
        """Design reward function for RL training.

        task_type: "reach", "pick_place", "manipulation", "locomotion"
        reward_components: dict of component_name -> {"weight": float, "params": dict}
        """
        if reward_components is None:
            if task_type == "reach":
                reward_components = {
                    "distance_to_goal": {"weight": 1.0, "params": {"sigma": 0.1}},
                    "action_penalty": {"weight": -0.01, "params": {}},
                    "success_bonus": {"weight": 5.0, "params": {"threshold": 0.02}},
                }
            elif task_type == "pick_place":
                reward_components = {
                    "reach_object": {"weight": 0.5, "params": {"sigma": 0.1}},
                    "grasp_reward": {"weight": 1.0, "params": {}},
                    "lift_reward": {"weight": 1.0, "params": {"height": 0.15}},
                    "place_reward": {"weight": 2.0, "params": {"sigma": 0.05}},
                    "action_penalty": {"weight": -0.005, "params": {}},
                    "success_bonus": {"weight": 10.0, "params": {"threshold": 0.03}},
                }
            elif task_type == "locomotion":
                reward_components = {
                    "forward_velocity": {"weight": 1.0, "params": {"target_vel": 1.0}},
                    "lateral_penalty": {"weight": -0.5, "params": {}},
                    "energy_penalty": {"weight": -0.01, "params": {}},
                    "alive_bonus": {"weight": 0.1, "params": {}},
                    "orientation_penalty": {"weight": -0.5, "params": {}},
                }
            else:
                reward_components = {
                    "task_progress": {"weight": 1.0, "params": {}},
                    "action_penalty": {"weight": -0.01, "params": {}},
                }

        # Generate reward function code
        reward_funcs = []
        for name, comp in reward_components.items():
            weight = comp["weight"]
            params = comp.get("params", {})

            if name == "distance_to_goal":
                sigma = params.get("sigma", 0.1)
                reward_funcs.append(f'''
    def _reward_distance_to_goal(self, env):
        """Exponential reward based on distance to goal."""
        ee_pos = env.robot.get_ee_position()
        goal_pos = env.goal_position
        dist = torch.norm(ee_pos - goal_pos, dim=-1)
        return torch.exp(-dist / {sigma})
''')
            elif name == "action_penalty":
                reward_funcs.append(f'''
    def _reward_action_penalty(self, env):
        """Penalize large actions for smooth motion."""
        return torch.sum(env.actions ** 2, dim=-1)
''')
            elif name == "success_bonus":
                threshold = params.get("threshold", 0.02)
                reward_funcs.append(f'''
    def _reward_success_bonus(self, env):
        """Bonus for reaching the goal."""
        ee_pos = env.robot.get_ee_position()
        goal_pos = env.goal_position
        dist = torch.norm(ee_pos - goal_pos, dim=-1)
        return (dist < {threshold}).float()
''')
            elif name == "forward_velocity":
                target = params.get("target_vel", 1.0)
                reward_funcs.append(f'''
    def _reward_forward_velocity(self, env):
        """Reward for maintaining target forward velocity."""
        vel = env.robot.get_base_velocity()[:, 0]  # x velocity
        return torch.exp(-torch.abs(vel - {target}))
''')
            elif name == "grasp_reward":
                reward_funcs.append('''
    def _reward_grasp(self, env):
        """Reward for successful grasping."""
        return env.robot.gripper_is_closed().float() * env.object_in_gripper().float()
''')
            elif name == "lift_reward":
                height = params.get("height", 0.15)
                reward_funcs.append(f'''
    def _reward_lift(self, env):
        """Reward for lifting object above threshold."""
        obj_height = env.object_position[:, 2]
        return (obj_height > {height}).float()
''')
            else:
                reward_funcs.append(f'''
    def _reward_{name}(self, env):
        """Custom reward: {name}."""
        return torch.zeros(env.num_envs, device=env.device)
''')

        # Build reward config
        weights_dict = {name: comp["weight"] for name, comp in reward_components.items()}

        code = f'''import torch
from omni.isaac.lab.managers import RewardTermCfg

class RewardFunction:
    """Task reward function with {len(reward_components)} components."""

    def __init__(self):
        self.weights = {json.dumps(weights_dict, indent=8)}

    def compute(self, env):
        """Compute total reward."""
        total = torch.zeros(env.num_envs, device=env.device)
{"".join(reward_funcs)}
        # Sum weighted components
'''
        for name in reward_components:
            code += f'        total += self.weights["{name}"] * self._reward_{name}(env)\n'

        code += '''
        return total

reward_fn = RewardFunction()
'''
        logger.info(f"Designed reward for {task_type}: {len(reward_components)} components")
        return {
            "code": code,
            "task_type": task_type,
            "components": reward_components,
            "weights": weights_dict,
        }

    def train_rl(self, env_config: dict = None, algo_config: dict = None) -> dict:
        """Generate RL training launch code.

        algo_config: {"algo": "PPO"|"SAC", "lr": float, "n_steps": int, ...}
        """
        env_config = env_config or {"task": "Isaac-Reach-Franka-v0", "num_envs": 4096}
        algo_config = algo_config or {
            "algo": "PPO",
            "learning_rate": 3e-4,
            "n_steps": 24,
            "batch_size": 24 * 4096,
            "n_epochs": 5,
            "clip_range": 0.2,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "max_iterations": 1500,
            "entropy_coef": 0.01,
            "value_loss_coef": 0.5,
            "network": {"mlp_dims": [256, 128, 64]},
        }

        output_dir = os.path.join(BASE_DIR, "training", "rl",
                                   env_config.get("task", "default"))

        code = f'''import torch
import os

# RL Training Configuration
env_config = {json.dumps(env_config, indent=4)}
algo_config = {json.dumps(algo_config, indent=4)}
output_dir = "{output_dir}"
os.makedirs(output_dir, exist_ok=True)

# Using RSL_RL (or rl_games) for Isaac Lab training
from omni.isaac.lab_tasks.utils import parse_env_cfg
from rsl_rl.runners import OnPolicyRunner

# Setup environment
env_cfg = parse_env_cfg(env_config["task"])
env_cfg.scene.num_envs = env_config["num_envs"]

# Configure PPO
runner_cfg = {{
    "algorithm": {{
        "class_name": algo_config["algo"],
        "learning_rate": algo_config["learning_rate"],
        "num_learning_epochs": algo_config["n_epochs"],
        "num_mini_batches": 8,
        "clip_param": algo_config["clip_range"],
        "gamma": algo_config["gamma"],
        "lam": algo_config["gae_lambda"],
        "entropy_coef": algo_config["entropy_coef"],
        "value_loss_coef": algo_config["value_loss_coef"],
    }},
    "policy": {{
        "class_name": "ActorCritic",
        "actor_hidden_dims": algo_config["network"]["mlp_dims"],
        "critic_hidden_dims": algo_config["network"]["mlp_dims"],
        "activation": "elu",
    }},
    "runner": {{
        "num_steps_per_env": algo_config["n_steps"],
        "max_iterations": algo_config["max_iterations"],
        "save_interval": 100,
        "log_interval": 10,
    }},
}}

import json
config_path = os.path.join(output_dir, "rl_config.json")
with open(config_path, "w") as f:
    json.dump(runner_cfg, f, indent=2)

print(f"RL Training configured:")
print(f"  Algorithm: {{algo_config['algo']}}")
print(f"  Envs: {{env_config['num_envs']}}")
print(f"  Max iterations: {{algo_config['max_iterations']}}")
print(f"  Output: {{output_dir}}")

# Launch training
runner = OnPolicyRunner(env, runner_cfg, output_dir, device="cuda:0")
runner.learn(num_learning_iterations=algo_config["max_iterations"])
'''
        logger.info(f"Configured RL training: {algo_config['algo']}, "
                     f"{algo_config['max_iterations']} iterations")
        return {
            "code": code,
            "env_config": env_config,
            "algo_config": algo_config,
            "output_dir": output_dir,
        }

    def evaluate_policy(self, checkpoint_path: str, n_episodes: int = 100,
                         deterministic: bool = True) -> dict:
        """Generate policy evaluation code."""
        code = f'''import torch
import numpy as np

checkpoint_path = "{checkpoint_path}"
n_episodes = {n_episodes}
deterministic = {deterministic}

# Load policy
policy = torch.jit.load(checkpoint_path)
policy.eval()

results = []
for ep in range(n_episodes):
    obs = env.reset()
    episode_reward = 0.0
    episode_length = 0

    done = False
    while not done:
        with torch.no_grad():
            if deterministic:
                action = policy.act_inference(obs)
            else:
                action = policy.act(obs)

        obs, reward, done, info = env.step(action)
        episode_reward += reward.mean().item()
        episode_length += 1

    results.append({{
        "reward": episode_reward,
        "length": episode_length,
        "success": info.get("success", False),
    }})

    if (ep + 1) % 20 == 0:
        sr = sum(r["success"] for r in results) / len(results)
        avg_r = sum(r["reward"] for r in results) / len(results)
        print(f"Episode {{ep+1}}/{{n_episodes}}: SR={{sr:.2%}}, Avg R={{avg_r:.2f}}")

# Summary
success_rate = sum(r["success"] for r in results) / len(results)
mean_reward = sum(r["reward"] for r in results) / len(results)
std_reward = np.std([r["reward"] for r in results])
mean_length = np.mean([r["length"] for r in results])

print(f"\\nEvaluation Complete:")
print(f"  Success Rate: {{success_rate:.2%}}")
print(f"  Mean Reward: {{mean_reward:.2f}} +/- {{std_reward:.2f}}")
print(f"  Mean Length: {{mean_length:.0f}}")

summary = {{
    "success_rate": success_rate,
    "mean_reward": mean_reward,
    "std_reward": std_reward,
    "mean_length": mean_length,
    "n_episodes": n_episodes,
    "deterministic": deterministic,
}}
'''
        logger.info(f"Generated eval code: {checkpoint_path}, {n_episodes} episodes")
        return {
            "code": code,
            "checkpoint_path": checkpoint_path,
            "n_episodes": n_episodes,
        }

    def transfer_to_groot(self, rl_checkpoint: str, groot_config: dict = None) -> dict:
        """Generate code to transfer RL-trained policy features to GR00T fine-tuning.

        Uses RL policy as a teacher for GR00T distillation.
        """
        groot_config = groot_config or {
            "distillation_epochs": 50,
            "distillation_lr": 5e-5,
            "temperature": 2.0,
            "alpha": 0.7,  # weight for distillation loss vs behavior cloning
        }

        code = f'''import torch
import torch.nn.functional as F
import os

rl_checkpoint = "{rl_checkpoint}"
groot_config = {json.dumps(groot_config, indent=4)}

# Load RL teacher policy
teacher = torch.jit.load(rl_checkpoint)
teacher.eval()
for p in teacher.parameters():
    p.requires_grad = False

# GR00T student model (assumed loaded)
# student = groot_model

optimizer = torch.optim.AdamW(
    student.parameters(),
    lr=groot_config["distillation_lr"],
    weight_decay=1e-5,
)

temperature = groot_config["temperature"]
alpha = groot_config["alpha"]

print(f"Starting RL->GR00T distillation:")
print(f"  Temperature: {{temperature}}")
print(f"  Alpha (distill vs BC): {{alpha}}")

for epoch in range(groot_config["distillation_epochs"]):
    epoch_loss = 0.0
    n_batches = 0

    for batch in dataloader:
        obs = batch["observation"].to("cuda:0")
        demo_actions = batch["action"].to("cuda:0")

        # Teacher predictions (RL policy)
        with torch.no_grad():
            teacher_actions = teacher.act_inference(obs)

        # Student predictions (GR00T)
        student_actions = student(obs)

        # Distillation loss (MSE between teacher and student outputs)
        distill_loss = F.mse_loss(student_actions, teacher_actions)

        # Behavior cloning loss (MSE to demonstration actions)
        bc_loss = F.mse_loss(student_actions, demo_actions)

        # Combined loss
        loss = alpha * distill_loss + (1 - alpha) * bc_loss

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
        optimizer.step()

        epoch_loss += loss.item()
        n_batches += 1

    avg_loss = epoch_loss / max(n_batches, 1)
    if (epoch + 1) % 5 == 0:
        print(f"Epoch {{epoch+1}}/{{groot_config['distillation_epochs']}}: "
              f"loss={{avg_loss:.6f}}")

# Save distilled model
output_path = os.path.join("{BASE_DIR}", "training", "groot_distilled")
os.makedirs(output_path, exist_ok=True)
torch.save(student.state_dict(), os.path.join(output_path, "distilled_policy.pt"))
print(f"Distilled policy saved to {{output_path}}")
'''
        logger.info(f"Generated RL->GR00T transfer: {rl_checkpoint}")
        return {
            "code": code,
            "rl_checkpoint": rl_checkpoint,
            "groot_config": groot_config,
        }
