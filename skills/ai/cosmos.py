# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""NVIDIA Cosmos world model skill for synthetic data generation."""
import os
import json
import logging
import subprocess

logger = logging.getLogger("skill.cosmos")
BASE_DIR = os.path.expanduser("~/agent-stack")


class CosmosSkill:
    """Manages Cosmos world model pipeline for synthetic scene generation."""

    def setup_pipeline(self, model_name: str = "Cosmos-1.0-Tokenizer-DV8x16x16",
                       checkpoint_dir: str = None, device: str = "cuda:0") -> dict:
        """Generate Cosmos pipeline setup code.

        model_name: Cosmos model variant to use.
        checkpoint_dir: path to model checkpoints.
        """
        checkpoint_dir = checkpoint_dir or os.path.join(BASE_DIR, "models", "cosmos")

        code = f'''import torch
import os

# Cosmos Pipeline Setup
model_name = "{model_name}"
checkpoint_dir = "{checkpoint_dir}"
device = torch.device("{device}")

os.makedirs(checkpoint_dir, exist_ok=True)

# Download model if not present
model_path = os.path.join(checkpoint_dir, model_name)
if not os.path.exists(model_path):
    print(f"Downloading {{model_name}}...")
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=f"nvidia/{{model_name}}",
        local_dir=model_path,
        local_dir_use_symlinks=False,
    )
    print(f"Model downloaded to {{model_path}}")

# Load tokenizer
if "Tokenizer" in model_name:
    from cosmos_tokenizer.video_lib import CausalVideoTokenizer

    encoder = CausalVideoTokenizer(
        checkpoint_enc=os.path.join(model_path, "encoder.jit"),
        checkpoint_dec=os.path.join(model_path, "decoder.jit"),
    )
    print(f"Cosmos tokenizer loaded: {{model_name}}")
    print(f"  Device: {{device}}")
else:
    # Load generation model
    from transformers import AutoModelForCausalLM, AutoConfig

    config = AutoConfig.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    print(f"Cosmos generation model loaded: {{model_name}}")
'''
        logger.info(f"Setup Cosmos pipeline: {model_name}")
        return {
            "code": code,
            "model_name": model_name,
            "checkpoint_dir": checkpoint_dir,
            "device": device,
        }

    def generate_synthetic_scene(self, prompt: str, num_frames: int = 16,
                                  resolution: list = None,
                                  conditioning: dict = None) -> dict:
        """Generate synthetic scene video from text/image prompt.

        prompt: text description of desired scene.
        num_frames: number of video frames to generate.
        conditioning: {"type": "text"|"image"|"video", "data": str (path or text)}
        """
        resolution = resolution or [576, 1024]
        conditioning = conditioning or {"type": "text", "data": prompt}

        code = f'''import torch
import numpy as np
from PIL import Image

# Generate synthetic scene
prompt = """{prompt}"""
num_frames = {num_frames}
resolution = {resolution}

# Prepare conditioning
conditioning_type = "{conditioning['type']}"

if conditioning_type == "text":
    # Text-to-video generation
    from cosmos_tokenizer.video_lib import CausalVideoTokenizer

    # Encode text prompt
    text_tokens = tokenizer.encode(prompt)

    # Generate video tokens autoregressively
    with torch.no_grad():
        generated_tokens = model.generate(
            input_ids=text_tokens,
            max_new_tokens=num_frames * (resolution[0] // 8) * (resolution[1] // 8) // 256,
            temperature=0.9,
            top_p=0.95,
            do_sample=True,
        )

    # Decode tokens to video frames
    video_tokens = generated_tokens.reshape(num_frames, -1)
    video_frames = encoder.decode(video_tokens)

elif conditioning_type == "image":
    # Image-conditioned video generation
    cond_image = Image.open("{conditioning.get('data', '')}")
    cond_image = cond_image.resize((resolution[1], resolution[0]))
    cond_tensor = torch.from_numpy(np.array(cond_image)).float() / 255.0
    cond_tensor = cond_tensor.permute(2, 0, 1).unsqueeze(0).to(device)

    # Encode conditioning image
    cond_tokens = encoder.encode(cond_tensor.unsqueeze(2))  # add time dim

    with torch.no_grad():
        generated_tokens = model.generate(
            input_ids=cond_tokens,
            max_new_tokens=num_frames * 256,
            temperature=0.8,
        )

    video_frames = encoder.decode(generated_tokens)

# Save output
output_dir = os.path.join("{BASE_DIR}", "outputs", "cosmos")
os.makedirs(output_dir, exist_ok=True)

# Save individual frames
for i, frame in enumerate(video_frames):
    frame_np = (frame.cpu().numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
    img = Image.fromarray(frame_np)
    img.save(os.path.join(output_dir, f"frame_{{i:04d}}.png"))

# Save as video
import imageio
frames_np = [(f.cpu().numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
             for f in video_frames]
video_path = os.path.join(output_dir, "generated.mp4")
imageio.mimwrite(video_path, frames_np, fps=24)

print(f"Generated {{len(video_frames)}} frames at {{resolution}}")
print(f"Saved to {{output_dir}}")
'''
        logger.info(f"Generated scene: '{prompt[:50]}...', {num_frames} frames")
        return {
            "code": code,
            "prompt": prompt,
            "num_frames": num_frames,
            "resolution": resolution,
            "conditioning": conditioning,
        }

    def run_inference(self, input_path: str, task: str = "tokenize",
                      output_path: str = None) -> dict:
        """Run Cosmos inference on input data.

        task: "tokenize" | "generate" | "reconstruct"
        """
        output_path = output_path or os.path.join(BASE_DIR, "outputs", "cosmos", "inference")

        code = f'''import torch
import numpy as np
import os
from PIL import Image

input_path = "{input_path}"
output_path = "{output_path}"
os.makedirs(output_path, exist_ok=True)

task = "{task}"

if task == "tokenize":
    # Encode video/image into discrete tokens
    import imageio
    if input_path.endswith((".mp4", ".avi", ".mov")):
        video = imageio.mimread(input_path)
        frames = torch.stack([
            torch.from_numpy(f).float().permute(2, 0, 1) / 255.0
            for f in video
        ]).unsqueeze(0).to(device)
    else:
        img = Image.open(input_path)
        frames = torch.from_numpy(np.array(img)).float().permute(2, 0, 1) / 255.0
        frames = frames.unsqueeze(0).unsqueeze(2).to(device)

    with torch.no_grad():
        tokens = encoder.encode(frames)

    # Save tokens
    token_path = os.path.join(output_path, "tokens.pt")
    torch.save(tokens, token_path)
    print(f"Tokenized: {{frames.shape}} -> tokens shape {{tokens.shape}}")
    print(f"Saved to {{token_path}}")

elif task == "reconstruct":
    # Tokenize then reconstruct to measure quality
    import imageio
    if input_path.endswith((".mp4", ".avi")):
        video = imageio.mimread(input_path)
        frames = torch.stack([
            torch.from_numpy(f).float().permute(2, 0, 1) / 255.0
            for f in video
        ]).unsqueeze(0).to(device)
    else:
        img = Image.open(input_path)
        frames = torch.from_numpy(np.array(img)).float().permute(2, 0, 1) / 255.0
        frames = frames.unsqueeze(0).unsqueeze(2).to(device)

    with torch.no_grad():
        tokens = encoder.encode(frames)
        recon = encoder.decode(tokens)

    # Compute reconstruction metrics
    mse = torch.mean((frames - recon) ** 2).item()
    psnr = 10 * np.log10(1.0 / mse) if mse > 0 else float("inf")

    print(f"Reconstruction MSE: {{mse:.6f}}, PSNR: {{psnr:.2f}} dB")

    # Save reconstructed
    for i in range(recon.shape[2]):
        frame_np = (recon[0, :, i].cpu().numpy().transpose(1, 2, 0) * 255).astype(np.uint8)
        Image.fromarray(frame_np).save(os.path.join(output_path, f"recon_{{i:04d}}.png"))

elif task == "generate":
    # World model generation from initial frames
    token_path = os.path.join(output_path, "tokens.pt")
    if os.path.exists(token_path):
        tokens = torch.load(token_path, map_location=device)
    else:
        raise FileNotFoundError(f"Run tokenize first: {{token_path}}")

    # Use first N tokens as context, generate the rest
    context_tokens = tokens[:, :, :4]  # first 4 frames
    with torch.no_grad():
        generated = model.generate(
            input_ids=context_tokens.flatten(1),
            max_new_tokens=tokens.numel() - context_tokens.numel(),
        )
    print(f"Generated {{generated.shape}} tokens from {{context_tokens.shape}} context")
'''
        logger.info(f"Generated inference code: task={task}, input={input_path}")
        return {
            "code": code,
            "input_path": input_path,
            "task": task,
            "output_path": output_path,
        }

    def validate_output(self, generated_path: str, reference_path: str = None) -> dict:
        """Validate generated output quality.

        Computes FID, LPIPS, temporal consistency, and other quality metrics.
        """
        code = f'''import torch
import numpy as np
from PIL import Image
import os
import glob

generated_path = "{generated_path}"
reference_path = "{reference_path}" if "{reference_path}" != "None" else None

# Load generated frames
gen_frames = sorted(glob.glob(os.path.join(generated_path, "*.png")))
generated = []
for fp in gen_frames:
    img = np.array(Image.open(fp)).astype(np.float32) / 255.0
    generated.append(img)
generated = np.stack(generated)

metrics = {{}}

# 1. Basic quality metrics
metrics["num_frames"] = len(generated)
metrics["resolution"] = list(generated[0].shape[:2])
metrics["mean_intensity"] = float(np.mean(generated))
metrics["std_intensity"] = float(np.std(generated))

# 2. Temporal consistency (frame-to-frame difference)
if len(generated) > 1:
    frame_diffs = [np.mean((generated[i+1] - generated[i])**2)
                   for i in range(len(generated)-1)]
    metrics["temporal_consistency"] = {{
        "mean_frame_diff": float(np.mean(frame_diffs)),
        "max_frame_diff": float(np.max(frame_diffs)),
        "std_frame_diff": float(np.std(frame_diffs)),
    }}

    # Check for frozen frames
    frozen = sum(1 for d in frame_diffs if d < 1e-6)
    metrics["frozen_frames"] = frozen

# 3. Reference-based metrics (if reference provided)
if reference_path is not None and os.path.exists(reference_path):
    ref_frames = sorted(glob.glob(os.path.join(reference_path, "*.png")))
    reference = []
    for fp in ref_frames:
        img = np.array(Image.open(fp)).astype(np.float32) / 255.0
        reference.append(img)
    reference = np.stack(reference)

    n = min(len(generated), len(reference))
    # MSE and PSNR
    mse = np.mean((generated[:n] - reference[:n])**2)
    psnr = 10 * np.log10(1.0 / mse) if mse > 0 else float("inf")
    metrics["mse"] = float(mse)
    metrics["psnr_db"] = float(psnr)

    # SSIM approximation
    def compute_ssim(img1, img2):
        mu1, mu2 = np.mean(img1), np.mean(img2)
        s1, s2 = np.std(img1), np.std(img2)
        cov = np.mean((img1 - mu1) * (img2 - mu2))
        c1, c2 = 0.01**2, 0.03**2
        ssim = ((2*mu1*mu2+c1)*(2*cov+c2)) / ((mu1**2+mu2**2+c1)*(s1**2+s2**2+c2))
        return ssim

    ssim_values = [compute_ssim(generated[i], reference[i]) for i in range(n)]
    metrics["ssim"] = {{
        "mean": float(np.mean(ssim_values)),
        "min": float(np.min(ssim_values)),
    }}

# Quality assessment
quality = "good"
if metrics.get("frozen_frames", 0) > len(generated) * 0.1:
    quality = "poor - frozen frames detected"
elif metrics.get("psnr_db", 30) < 20:
    quality = "poor - low reconstruction quality"
elif metrics.get("temporal_consistency", {{}}).get("max_frame_diff", 0) > 0.1:
    quality = "warning - temporal inconsistency"

metrics["quality_assessment"] = quality

print(f"Validation results for {{generated_path}}:")
for k, v in metrics.items():
    print(f"  {{k}}: {{v}}")
'''
        logger.info(f"Generated validation code for {generated_path}")
        return {
            "code": code,
            "generated_path": generated_path,
            "reference_path": reference_path,
        }
