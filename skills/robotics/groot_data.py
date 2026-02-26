# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""GR00T data generation and formatting skill."""
import os
import json
import math
import logging

logger = logging.getLogger("skill.groot_data")
BASE_DIR = os.path.expanduser("~/agent-stack")


class GrootDataSkill:
    """Generates and formats trajectory datasets for GR00T training."""

    def generate_trajectory_dataset(self, task_config: dict = None,
                                     n_episodes: int = 100,
                                     output_dir: str = None) -> dict:
        """Generate trajectory dataset from Isaac Sim task runs.

        task_config: {"task_name": str, "robot": str, "environment": str,
                      "randomize": bool, "max_steps": int}
        """
        task_config = task_config or {
            "task_name": "pick_and_place",
            "robot": "ur10e",
            "environment": "tabletop",
            "randomize": True,
            "max_steps": 500,
        }
        output_dir = output_dir or os.path.join(BASE_DIR, "data", "trajectories",
                                                  task_config.get("task_name", "default"))

        code = f'''import numpy as np
import json
import os
import h5py

output_dir = "{output_dir}"
os.makedirs(output_dir, exist_ok=True)

task_config = {json.dumps(task_config, indent=4)}
n_episodes = {n_episodes}

# Data storage
dataset = {{
    "metadata": {{
        "task": task_config["task_name"],
        "robot": task_config["robot"],
        "n_episodes": n_episodes,
        "max_steps": task_config["max_steps"],
        "observation_keys": [
            "joint_positions", "joint_velocities", "ee_position",
            "ee_orientation", "gripper_state", "rgb_image", "depth_image",
        ],
        "action_keys": ["joint_position_targets", "gripper_command"],
    }},
    "episodes": [],
}}

for ep in range(n_episodes):
    if task_config["randomize"]:
        domain_randomizer.apply_all(stage, robot, sensors)

    # Reset environment
    world.reset()
    episode_data = {{
        "observations": [],
        "actions": [],
        "rewards": [],
        "dones": [],
        "info": {{"episode_id": ep}},
    }}

    for step in range(task_config["max_steps"]):
        # Collect observation
        obs = {{
            "joint_positions": robot.get_joint_positions().tolist(),
            "joint_velocities": robot.get_joint_velocities().tolist(),
            "ee_position": robot.get_ee_position().tolist(),
            "ee_orientation": robot.get_ee_orientation().tolist(),
            "gripper_state": robot.get_gripper_state(),
        }}

        # Get action from policy or demonstration
        action = policy.get_action(obs)

        # Step environment
        robot.apply_action(action)
        world.step(render=True)

        # Compute reward
        reward = task.compute_reward()
        done = task.check_termination()

        episode_data["observations"].append(obs)
        episode_data["actions"].append(action)
        episode_data["rewards"].append(reward)
        episode_data["dones"].append(done)

        if done:
            break

    episode_data["info"]["length"] = len(episode_data["observations"])
    episode_data["info"]["total_reward"] = sum(episode_data["rewards"])
    episode_data["info"]["success"] = task.check_success()
    dataset["episodes"].append(episode_data)

    if (ep + 1) % 10 == 0:
        print(f"Episode {{ep+1}}/{{n_episodes}}: "
              f"len={{episode_data['info']['length']}}, "
              f"reward={{episode_data['info']['total_reward']:.2f}}, "
              f"success={{episode_data['info']['success']}}")

# Save as HDF5
h5_path = os.path.join(output_dir, "dataset.hdf5")
with h5py.File(h5_path, "w") as f:
    f.attrs["metadata"] = json.dumps(dataset["metadata"])
    for i, ep in enumerate(dataset["episodes"]):
        grp = f.create_group(f"episode_{{i:05d}}")
        for key in ep["observations"][0].keys():
            data = np.array([obs[key] for obs in ep["observations"]])
            grp.create_dataset(f"obs/{{key}}", data=data, compression="gzip")
        grp.create_dataset("actions", data=np.array(ep["actions"]), compression="gzip")
        grp.create_dataset("rewards", data=np.array(ep["rewards"]))
        grp.create_dataset("dones", data=np.array(ep["dones"]))
        grp.attrs["info"] = json.dumps(ep["info"])

# Save metadata
with open(os.path.join(output_dir, "metadata.json"), "w") as f:
    json.dump(dataset["metadata"], f, indent=2)

print(f"Dataset saved: {{n_episodes}} episodes to {{output_dir}}")
'''
        logger.info(f"Generated dataset code: {n_episodes} episodes for {task_config.get('task_name')}")
        return {
            "code": code,
            "output_dir": output_dir,
            "task_config": task_config,
            "n_episodes": n_episodes,
        }

    def validate_dataset(self, dataset_path: str) -> dict:
        """Validate dataset quality: check for missing data, NaN values,
        distribution statistics, and format compliance."""
        code = f'''import h5py
import numpy as np
import json
import os

dataset_path = "{dataset_path}"
issues = []
stats = {{}}

if dataset_path.endswith(".hdf5"):
    with h5py.File(dataset_path, "r") as f:
        metadata = json.loads(f.attrs.get("metadata", "{{}}"))
        n_episodes = len([k for k in f.keys() if k.startswith("episode")])

        episode_lengths = []
        rewards = []
        success_count = 0
        nan_count = 0
        total_steps = 0

        for ep_key in sorted(f.keys()):
            if not ep_key.startswith("episode"):
                continue
            grp = f[ep_key]
            info = json.loads(grp.attrs.get("info", "{{}}"))
            ep_len = info.get("length", 0)
            episode_lengths.append(ep_len)
            total_steps += ep_len

            if info.get("success", False):
                success_count += 1

            if "rewards" in grp:
                ep_rewards = grp["rewards"][:]
                rewards.extend(ep_rewards.tolist())
                if np.any(np.isnan(ep_rewards)):
                    issues.append(f"NaN in rewards for {{ep_key}}")
                    nan_count += 1

            # Check observations for NaN
            if "obs" in grp:
                for obs_key in grp["obs"].keys():
                    data = grp["obs"][obs_key][:]
                    if np.any(np.isnan(data)):
                        issues.append(f"NaN in obs/{{obs_key}} for {{ep_key}}")
                        nan_count += 1
                    if np.any(np.isinf(data)):
                        issues.append(f"Inf in obs/{{obs_key}} for {{ep_key}}")

            # Check actions
            if "actions" in grp:
                actions = grp["actions"][:]
                if np.any(np.isnan(actions)):
                    issues.append(f"NaN in actions for {{ep_key}}")
                    nan_count += 1

        stats = {{
            "n_episodes": n_episodes,
            "total_steps": total_steps,
            "mean_episode_length": float(np.mean(episode_lengths)) if episode_lengths else 0,
            "std_episode_length": float(np.std(episode_lengths)) if episode_lengths else 0,
            "min_episode_length": int(min(episode_lengths)) if episode_lengths else 0,
            "max_episode_length": int(max(episode_lengths)) if episode_lengths else 0,
            "success_rate": success_count / n_episodes if n_episodes > 0 else 0,
            "mean_reward": float(np.mean(rewards)) if rewards else 0,
            "std_reward": float(np.std(rewards)) if rewards else 0,
            "nan_count": nan_count,
        }}

        print(f"Dataset validation: {{dataset_path}}")
        print(f"  Episodes: {{n_episodes}}")
        print(f"  Total steps: {{total_steps}}")
        print(f"  Success rate: {{stats['success_rate']:.2%}}")
        print(f"  Issues: {{len(issues)}}")
        for issue in issues[:10]:
            print(f"    - {{issue}}")
'''
        logger.info(f"Generated validation code for {dataset_path}")
        return {
            "code": code,
            "dataset_path": dataset_path,
        }

    def format_for_groot(self, input_path: str, output_path: str = None,
                          format_config: dict = None) -> dict:
        """Format dataset in LeRobot-compatible format for GR00T training.

        Converts HDF5 dataset to the LeRobot dataset format expected by GR00T.
        """
        output_path = output_path or os.path.join(BASE_DIR, "data", "groot_formatted")
        format_config = format_config or {
            "fps": 30,
            "image_size": [224, 224],
            "action_space": "joint_position",
            "include_language": True,
            "task_description": "Pick up the object and place it in the target location.",
        }

        code = f'''import h5py
import numpy as np
import json
import os
from pathlib import Path
from PIL import Image

input_path = "{input_path}"
output_path = "{output_path}"
os.makedirs(output_path, exist_ok=True)

config = {json.dumps(format_config, indent=4)}

# LeRobot dataset structure
# output_path/
#   meta/
#     info.json
#     episodes.jsonl
#     stats.json
#     tasks.jsonl
#   data/
#     chunk-000/
#       episode_000000.parquet

# Read source dataset
with h5py.File(input_path, "r") as f:
    metadata = json.loads(f.attrs.get("metadata", "{{}}"))
    episode_keys = sorted([k for k in f.keys() if k.startswith("episode")])

    # Create metadata
    info = {{
        "codebase_version": "v2.1",
        "robot_type": metadata.get("robot", "unknown"),
        "fps": config["fps"],
        "features": {{
            "observation.state": {{
                "dtype": "float32",
                "shape": [metadata.get("n_dof", 7)],
                "names": ["joint_positions"],
            }},
            "action": {{
                "dtype": "float32",
                "shape": [metadata.get("n_dof", 7)],
                "names": ["joint_position_targets"],
            }},
        }},
        "splits": {{"train": f"0:{{int(len(episode_keys)*0.9)}}",
                    "eval": f"{{int(len(episode_keys)*0.9)}}:{{len(episode_keys)}}"}},
    }}

    if config.get("include_language"):
        info["features"]["language_instruction"] = {{
            "dtype": "string",
            "shape": [1],
        }}

    os.makedirs(os.path.join(output_path, "meta"), exist_ok=True)
    with open(os.path.join(output_path, "meta", "info.json"), "w") as mf:
        json.dump(info, mf, indent=2)

    # Write tasks
    with open(os.path.join(output_path, "meta", "tasks.jsonl"), "w") as tf:
        tf.write(json.dumps({{
            "task_index": 0,
            "task": config.get("task_description", ""),
        }}) + "\\n")

    # Convert episodes
    os.makedirs(os.path.join(output_path, "data", "chunk-000"), exist_ok=True)
    episodes_meta = []

    for ep_idx, ep_key in enumerate(episode_keys):
        grp = f[ep_key]
        info_ep = json.loads(grp.attrs.get("info", "{{}}"))

        # Extract data
        if "obs/joint_positions" in grp:
            states = grp["obs/joint_positions"][:]
        else:
            states = np.zeros((info_ep.get("length", 1), 7))

        if "actions" in grp:
            actions = grp["actions"][:]
        else:
            actions = states.copy()

        # Save as parquet-compatible format (using numpy for now)
        ep_data = {{
            "observation.state": states.tolist(),
            "action": actions.tolist(),
        }}
        if config.get("include_language"):
            ep_data["language_instruction"] = [config["task_description"]] * len(states)

        ep_path = os.path.join(output_path, "data", "chunk-000",
                               f"episode_{{ep_idx:06d}}.json")
        with open(ep_path, "w") as ef:
            json.dump(ep_data, ef)

        episodes_meta.append({{
            "episode_index": ep_idx,
            "length": len(states),
            "task_index": 0,
        }})

    # Write episodes metadata
    with open(os.path.join(output_path, "meta", "episodes.jsonl"), "w") as ef:
        for em in episodes_meta:
            ef.write(json.dumps(em) + "\\n")

    print(f"Formatted {{len(episode_keys)}} episodes for GR00T training")
    print(f"Output: {{output_path}}")
'''
        logger.info(f"Generated GR00T formatting code: {input_path} -> {output_path}")
        return {
            "code": code,
            "input_path": input_path,
            "output_path": output_path,
            "format_config": format_config,
        }
