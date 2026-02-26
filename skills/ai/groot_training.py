# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""GR00T training skill for humanoid robot policy learning."""
import os
import json
import logging

logger = logging.getLogger("skill.groot_training")
BASE_DIR = os.path.expanduser("~/agent-stack")


class GrootTrainingSkill:
    """Manages GR00T policy training pipeline: data prep, training, evaluation, export."""

    def prepare_lerobot_dataset(self, raw_data_path: str, output_path: str = None,
                                 config: dict = None) -> dict:
        """Prepare raw demonstration data into LeRobot dataset format.

        raw_data_path: path to raw HDF5 or directory of episode files.
        """
        output_path = output_path or os.path.join(BASE_DIR, "data", "lerobot_dataset")
        config = config or {
            "fps": 30,
            "image_keys": ["rgb_front", "rgb_wrist"],
            "state_keys": ["joint_positions", "joint_velocities", "ee_position"],
            "action_key": "joint_position_targets",
            "chunk_size": 1000,
        }

        code = f'''import h5py
import numpy as np
import json
import os
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

raw_path = "{raw_data_path}"
output_path = "{output_path}"
config = {json.dumps(config, indent=4)}

os.makedirs(output_path, exist_ok=True)
os.makedirs(os.path.join(output_path, "meta"), exist_ok=True)
os.makedirs(os.path.join(output_path, "data", "chunk-000"), exist_ok=True)
os.makedirs(os.path.join(output_path, "videos"), exist_ok=True)

# Read raw data
with h5py.File(raw_path, "r") as f:
    episode_keys = sorted([k for k in f.keys() if k.startswith("episode")])
    total_frames = 0
    episodes_info = []

    for ep_idx, ep_key in enumerate(episode_keys):
        grp = f[ep_key]
        ep_info = json.loads(grp.attrs.get("info", "{{}}"))
        ep_len = ep_info.get("length", 0)

        # Build per-frame records
        records = []
        for step in range(ep_len):
            record = {{
                "episode_index": ep_idx,
                "frame_index": step,
                "timestamp": step / config["fps"],
                "task_index": 0,
                "index": total_frames + step,
            }}

            # State observations
            for state_key in config["state_keys"]:
                if f"obs/{{state_key}}" in grp:
                    data = grp[f"obs/{{state_key}}"][step]
                    record[f"observation.state.{{state_key}}"] = data.tolist()

            # Action
            if config["action_key"] in grp.get("actions", {{}}).keys() if hasattr(grp.get("actions", {{}}), 'keys') else "actions" in grp:
                actions = grp["actions"]
                if step < len(actions):
                    record["action"] = actions[step].tolist()

            records.append(record)

        # Write episode to parquet
        if records:
            table = pa.table({{
                k: [r.get(k) for r in records]
                for k in records[0].keys()
                if not isinstance(records[0][k], list)
            }})

            chunk_idx = ep_idx // config["chunk_size"]
            chunk_dir = os.path.join(output_path, "data", f"chunk-{{chunk_idx:03d}}")
            os.makedirs(chunk_dir, exist_ok=True)
            pq.write_table(table, os.path.join(chunk_dir, f"episode_{{ep_idx:06d}}.parquet"))

        episodes_info.append({{
            "episode_index": ep_idx,
            "length": ep_len,
            "task_index": 0,
        }})
        total_frames += ep_len

    # Write metadata
    meta = {{
        "codebase_version": "v2.1",
        "fps": config["fps"],
        "total_episodes": len(episode_keys),
        "total_frames": total_frames,
        "features": {{
            f"observation.state.{{k}}": {{"dtype": "float32"}} for k in config["state_keys"]
        }},
    }}
    meta["features"]["action"] = {{"dtype": "float32"}}

    with open(os.path.join(output_path, "meta", "info.json"), "w") as mf:
        json.dump(meta, mf, indent=2)

    with open(os.path.join(output_path, "meta", "episodes.jsonl"), "w") as ef:
        for ei in episodes_info:
            ef.write(json.dumps(ei) + "\\n")

    print(f"LeRobot dataset prepared: {{len(episode_keys)}} episodes, {{total_frames}} frames")
    print(f"Output: {{output_path}}")
'''
        logger.info(f"Generated LeRobot prep code: {raw_data_path} -> {output_path}")
        return {
            "code": code,
            "raw_data_path": raw_data_path,
            "output_path": output_path,
            "config": config,
        }

    def validate_dataset(self, dataset_path: str) -> dict:
        """Validate LeRobot dataset for GR00T training compatibility."""
        code = f'''import json
import os
from pathlib import Path
import pyarrow.parquet as pq

dataset_path = "{dataset_path}"
issues = []
warnings = []

# Check required files
required_files = [
    "meta/info.json",
    "meta/episodes.jsonl",
]
for rf in required_files:
    if not os.path.exists(os.path.join(dataset_path, rf)):
        issues.append(f"Missing required file: {{rf}}")

# Load and validate info.json
info_path = os.path.join(dataset_path, "meta", "info.json")
if os.path.exists(info_path):
    with open(info_path) as f:
        info = json.load(f)

    if "fps" not in info:
        issues.append("Missing 'fps' in info.json")
    elif info["fps"] < 1 or info["fps"] > 120:
        warnings.append(f"Unusual fps: {{info['fps']}}")

    if "features" not in info:
        issues.append("Missing 'features' in info.json")
    else:
        if "action" not in info["features"]:
            issues.append("Missing 'action' feature definition")

        has_state = any("observation.state" in k for k in info["features"])
        if not has_state:
            issues.append("No observation.state features defined")

    total_episodes = info.get("total_episodes", 0)
    total_frames = info.get("total_frames", 0)
else:
    total_episodes = 0
    total_frames = 0
    info = {{}}

# Validate episodes
episodes_path = os.path.join(dataset_path, "meta", "episodes.jsonl")
if os.path.exists(episodes_path):
    episode_count = 0
    total_length = 0
    with open(episodes_path) as f:
        for line in f:
            ep = json.loads(line.strip())
            episode_count += 1
            total_length += ep.get("length", 0)

    if total_episodes > 0 and episode_count != total_episodes:
        warnings.append(f"Episode count mismatch: meta says {{total_episodes}}, found {{episode_count}}")
else:
    episode_count = 0
    total_length = 0

# Check data files
data_dir = os.path.join(dataset_path, "data")
parquet_files = list(Path(data_dir).rglob("*.parquet")) if os.path.exists(data_dir) else []

if len(parquet_files) == 0:
    issues.append("No parquet data files found")
else:
    # Validate first parquet file
    sample = pq.read_table(str(parquet_files[0]))
    columns = sample.column_names
    if "action" not in columns:
        issues.append("'action' column missing from data")
    has_state_col = any("observation.state" in c for c in columns)
    if not has_state_col:
        warnings.append("No observation.state columns in data")

validation = {{
    "valid": len(issues) == 0,
    "issues": issues,
    "warnings": warnings,
    "stats": {{
        "episodes": episode_count,
        "total_frames": total_length,
        "parquet_files": len(parquet_files),
        "features": list(info.get("features", {{}}).keys()),
    }},
}}

print(f"Dataset validation: {{'PASS' if validation['valid'] else 'FAIL'}}")
print(f"  Episodes: {{episode_count}}, Frames: {{total_length}}")
if issues:
    print(f"  Issues ({{len(issues)}}):")
    for i in issues:
        print(f"    - {{i}}")
if warnings:
    print(f"  Warnings ({{len(warnings)}}):")
    for w in warnings:
        print(f"    - {{w}}")
'''
        logger.info(f"Generated dataset validation for {dataset_path}")
        return {"code": code, "dataset_path": dataset_path}

    def configure_training(self, dataset_path: str, config: dict = None) -> dict:
        """Generate GR00T training configuration.

        config: training hyperparameters override.
        """
        config = config or {}
        training_config = {
            "model": config.get("model", "gr00t-n1-2"),
            "dataset_path": dataset_path,
            "batch_size": config.get("batch_size", 32),
            "learning_rate": config.get("learning_rate", 1e-4),
            "weight_decay": config.get("weight_decay", 1e-5),
            "num_epochs": config.get("num_epochs", 100),
            "warmup_steps": config.get("warmup_steps", 1000),
            "gradient_clip": config.get("gradient_clip", 1.0),
            "action_head": config.get("action_head", "diffusion"),
            "observation_horizon": config.get("observation_horizon", 2),
            "action_horizon": config.get("action_horizon", 16),
            "prediction_horizon": config.get("prediction_horizon", 16),
            "num_diffusion_steps": config.get("num_diffusion_steps", 100),
            "mixed_precision": config.get("mixed_precision", "bf16"),
            "checkpoint_interval": config.get("checkpoint_interval", 10),
            "eval_interval": config.get("eval_interval", 5),
            "output_dir": config.get("output_dir",
                                      os.path.join(BASE_DIR, "training", "groot")),
        }

        code = f'''import json
import os

# GR00T Training Configuration
config = {json.dumps(training_config, indent=4)}

output_dir = config["output_dir"]
os.makedirs(output_dir, exist_ok=True)

# Save config
config_path = os.path.join(output_dir, "training_config.json")
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)

# Launch training
import subprocess
cmd = [
    "python", "-m", "gr00t.train",
    "--dataset-path", config["dataset_path"],
    "--model", config["model"],
    "--batch-size", str(config["batch_size"]),
    "--learning-rate", str(config["learning_rate"]),
    "--num-epochs", str(config["num_epochs"]),
    "--action-head", config["action_head"],
    "--observation-horizon", str(config["observation_horizon"]),
    "--action-horizon", str(config["action_horizon"]),
    "--prediction-horizon", str(config["prediction_horizon"]),
    "--mixed-precision", config["mixed_precision"],
    "--output-dir", output_dir,
    "--checkpoint-interval", str(config["checkpoint_interval"]),
    "--eval-interval", str(config["eval_interval"]),
    "--gradient-clip", str(config["gradient_clip"]),
    "--warmup-steps", str(config["warmup_steps"]),
]

print(f"Training command: {{' '.join(cmd)}}")
print(f"Config saved to: {{config_path}}")
'''
        logger.info(f"Configured GR00T training: {training_config['num_epochs']} epochs")
        return {
            "code": code,
            "config": training_config,
        }

    def monitor_metrics(self, training_dir: str = None) -> dict:
        """Generate code to monitor training metrics from log files."""
        training_dir = training_dir or os.path.join(BASE_DIR, "training", "groot")

        code = f'''import json
import os
import glob

training_dir = "{training_dir}"

# Find latest log file
log_files = sorted(glob.glob(os.path.join(training_dir, "**", "metrics.jsonl"),
                              recursive=True))
if not log_files:
    print("No metrics files found")
else:
    latest_log = log_files[-1]
    metrics = []
    with open(latest_log) as f:
        for line in f:
            metrics.append(json.loads(line.strip()))

    if metrics:
        latest = metrics[-1]
        print(f"Training Progress ({{latest_log}}):")
        print(f"  Epoch: {{latest.get('epoch', '?')}}")
        print(f"  Step: {{latest.get('step', '?')}}")
        print(f"  Train Loss: {{latest.get('train_loss', '?')}}")
        print(f"  Val Loss: {{latest.get('val_loss', '?')}}")
        print(f"  Learning Rate: {{latest.get('learning_rate', '?')}}")
        print(f"  Action MSE: {{latest.get('action_mse', '?')}}")

        # Compute trends
        if len(metrics) > 10:
            recent_train = [m["train_loss"] for m in metrics[-10:] if "train_loss" in m]
            older_train = [m["train_loss"] for m in metrics[-20:-10] if "train_loss" in m]
            if recent_train and older_train:
                improvement = (sum(older_train)/len(older_train) -
                              sum(recent_train)/len(recent_train))
                print(f"  Loss improvement (last 10 vs prev 10): {{improvement:.6f}}")

                if improvement < 0:
                    print("  WARNING: Loss is increasing - consider reducing learning rate")
                elif improvement < 1e-6:
                    print("  NOTE: Loss plateau detected - may need schedule adjustment")

# Check for checkpoints
ckpt_files = sorted(glob.glob(os.path.join(training_dir, "**", "checkpoint_*.pt"),
                                recursive=True))
if ckpt_files:
    print(f"\\nCheckpoints ({{len(ckpt_files)}}):")
    for ckpt in ckpt_files[-5:]:
        size_mb = os.path.getsize(ckpt) / (1024 * 1024)
        print(f"  {{os.path.basename(ckpt)}} ({{size_mb:.1f}} MB)")
'''
        logger.info(f"Generated metrics monitor for {training_dir}")
        return {"code": code, "training_dir": training_dir}

    def evaluate_in_sim(self, checkpoint_path: str, eval_config: dict = None) -> dict:
        """Generate code to evaluate trained policy in Isaac Sim."""
        eval_config = eval_config or {
            "n_episodes": 50,
            "max_steps": 500,
            "render": False,
            "record_video": True,
        }

        code = f'''import torch
import numpy as np
import json
import os

checkpoint_path = "{checkpoint_path}"
eval_config = {json.dumps(eval_config, indent=4)}

# Load trained policy
policy = torch.jit.load(checkpoint_path)
policy.eval()
policy.to("cuda:0")

results = {{
    "episodes": [],
    "successes": 0,
    "total_reward": 0.0,
}}

for ep in range(eval_config["n_episodes"]):
    world.reset()
    episode_reward = 0.0
    episode_data = {{"actions": [], "rewards": [], "observations": []}}

    obs_history = []
    for step in range(eval_config["max_steps"]):
        obs = get_observation()
        obs_history.append(obs)

        # Use observation horizon
        obs_window = obs_history[-2:]  # last 2 observations
        obs_tensor = torch.tensor(
            np.stack([o["state"] for o in obs_window]),
            dtype=torch.float32, device="cuda:0"
        ).unsqueeze(0)

        with torch.no_grad():
            action_chunk = policy(obs_tensor)

        # Execute first action from chunk
        action = action_chunk[0, 0].cpu().numpy()
        robot.apply_action(action)
        world.step(render=eval_config["render"])

        reward = task.compute_reward()
        episode_reward += reward
        done = task.check_termination()

        episode_data["actions"].append(action.tolist())
        episode_data["rewards"].append(reward)

        if done:
            break

    success = task.check_success()
    results["episodes"].append({{
        "reward": episode_reward,
        "length": step + 1,
        "success": success,
    }})
    if success:
        results["successes"] += 1
    results["total_reward"] += episode_reward

    if (ep + 1) % 10 == 0:
        sr = results["successes"] / (ep + 1)
        avg_r = results["total_reward"] / (ep + 1)
        print(f"Episode {{ep+1}}/{{eval_config['n_episodes']}}: SR={{sr:.2%}}, Avg R={{avg_r:.2f}}")

# Summary
n = eval_config["n_episodes"]
results["summary"] = {{
    "success_rate": results["successes"] / n,
    "mean_reward": results["total_reward"] / n,
    "mean_length": np.mean([e["length"] for e in results["episodes"]]),
    "std_reward": np.std([e["reward"] for e in results["episodes"]]),
}}

print(f"\\nEvaluation Summary:")
print(f"  Success Rate: {{results['summary']['success_rate']:.2%}}")
print(f"  Mean Reward: {{results['summary']['mean_reward']:.2f}}")
print(f"  Mean Length: {{results['summary']['mean_length']:.0f}}")
'''
        logger.info(f"Generated sim eval for {checkpoint_path}")
        return {
            "code": code,
            "checkpoint_path": checkpoint_path,
            "eval_config": eval_config,
        }

    def export_for_deployment(self, checkpoint_path: str, output_path: str = None,
                               target: str = "jetson") -> dict:
        """Export trained model for deployment on target hardware."""
        output_path = output_path or os.path.join(BASE_DIR, "deploy", "groot_policy")

        code = f'''import torch
import os

checkpoint_path = "{checkpoint_path}"
output_path = "{output_path}"
target = "{target}"
os.makedirs(output_path, exist_ok=True)

# Load checkpoint
checkpoint = torch.load(checkpoint_path, map_location="cpu")
if "model_state_dict" in checkpoint:
    model.load_state_dict(checkpoint["model_state_dict"])
else:
    model.load_state_dict(checkpoint)

model.eval()

# Export based on target
if target == "jetson":
    # Export as TorchScript for Jetson deployment
    example_obs = torch.randn(1, 2, model.obs_dim)  # batch, horizon, obs_dim
    traced = torch.jit.trace(model, example_obs)
    script_path = os.path.join(output_path, "policy.pt")
    traced.save(script_path)
    print(f"TorchScript exported: {{script_path}}")

    # Also export as ONNX for TensorRT
    onnx_path = os.path.join(output_path, "policy.onnx")
    torch.onnx.export(
        model,
        example_obs,
        onnx_path,
        input_names=["observation"],
        output_names=["action"],
        dynamic_axes={{"observation": {{0: "batch"}}, "action": {{0: "batch"}}}},
        opset_version=17,
    )
    print(f"ONNX exported: {{onnx_path}}")

    # Generate TensorRT conversion script
    trt_script = f\"\"\"
#!/bin/bash
# Convert ONNX to TensorRT engine on Jetson
/usr/src/tensorrt/bin/trtexec \\\\
    --onnx={{onnx_path}} \\\\
    --saveEngine={{os.path.join(output_path, 'policy.engine')}} \\\\
    --fp16 \\\\
    --workspace=4096
\"\"\"
    trt_path = os.path.join(output_path, "build_trt.sh")
    with open(trt_path, "w") as f:
        f.write(trt_script)
    os.chmod(trt_path, 0o755)
    print(f"TensorRT build script: {{trt_path}}")

elif target == "cpu":
    traced = torch.jit.trace(model, torch.randn(1, 2, model.obs_dim))
    script_path = os.path.join(output_path, "policy_cpu.pt")
    traced.save(script_path)
    print(f"CPU model exported: {{script_path}}")

# Save deployment metadata
metadata = {{
    "source_checkpoint": checkpoint_path,
    "target": target,
    "obs_dim": model.obs_dim if hasattr(model, 'obs_dim') else "unknown",
    "action_dim": model.action_dim if hasattr(model, 'action_dim') else "unknown",
    "exported_files": os.listdir(output_path),
}}
with open(os.path.join(output_path, "deployment_info.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print(f"Deployment package ready at {{output_path}}")
'''
        logger.info(f"Generated export for {target}: {checkpoint_path}")
        return {
            "code": code,
            "checkpoint_path": checkpoint_path,
            "output_path": output_path,
            "target": target,
        }
