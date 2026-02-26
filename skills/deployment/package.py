# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Deployment packaging skill."""
import os
import json
import hashlib
import logging
import subprocess
import time

logger = logging.getLogger("skill.package")
BASE_DIR = os.path.expanduser("~/agent-stack")


class PackageSkill:
    """Packages trained policies for deployment with validation and signing."""

    def package_policy(self, policy_path: str, metadata: dict = None,
                       output_dir: str = None) -> dict:
        """Package a trained policy with all necessary artifacts for deployment.

        policy_path: path to trained model file (.pt, .onnx, etc.)
        metadata: {"version": str, "robot": str, "task": str, ...}
        """
        metadata = metadata or {}
        version = metadata.get("version", "0.1.0")
        robot = metadata.get("robot", "unknown")
        task = metadata.get("task", "unknown")
        output_dir = output_dir or os.path.join(BASE_DIR, "deploy", "packages",
                                                  f"{task}-v{version}")

        os.makedirs(output_dir, exist_ok=True)

        # Collect files to package
        files_to_include = []

        # Copy policy file
        policy_filename = os.path.basename(policy_path)
        dest_policy = os.path.join(output_dir, policy_filename)
        if os.path.exists(policy_path):
            with open(policy_path, "rb") as src:
                content = src.read()
            with open(dest_policy, "wb") as dst:
                dst.write(content)
            files_to_include.append(policy_filename)
            policy_size = len(content)
        else:
            policy_size = 0
            logger.warning(f"Policy file not found: {policy_path}")

        # Generate deployment manifest
        manifest = {
            "package_version": "1.0",
            "policy": {
                "file": policy_filename,
                "format": os.path.splitext(policy_filename)[1],
                "size_bytes": policy_size,
            },
            "metadata": {
                "version": version,
                "robot": robot,
                "task": task,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "created_by": "agent-stack",
                **{k: v for k, v in metadata.items()
                   if k not in ("version", "robot", "task")},
            },
            "requirements": {
                "python": metadata.get("python_version", ">=3.10"),
                "torch": metadata.get("torch_version", ">=2.0"),
                "platform": metadata.get("platform", "linux-aarch64"),
            },
            "files": files_to_include,
        }

        manifest_path = os.path.join(output_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        files_to_include.append("manifest.json")

        # Generate deployment script
        deploy_script = f'''#!/bin/bash
# Auto-generated deployment script for {task} v{version}
set -e

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
DEPLOY_DIR="${{DEPLOY_DIR:-/opt/robot/policies/{task}}}"

echo "Deploying {task} v{version} to $DEPLOY_DIR"

mkdir -p "$DEPLOY_DIR"
cp "$SCRIPT_DIR/{policy_filename}" "$DEPLOY_DIR/"
cp "$SCRIPT_DIR/manifest.json" "$DEPLOY_DIR/"

# Verify integrity
echo "Verifying package integrity..."
EXPECTED_HASH=$(cat "$SCRIPT_DIR/checksums.sha256" | grep {policy_filename} | awk '{{print $1}}')
ACTUAL_HASH=$(sha256sum "$DEPLOY_DIR/{policy_filename}" | awk '{{print $1}}')

if [ "$EXPECTED_HASH" = "$ACTUAL_HASH" ]; then
    echo "Integrity check PASSED"
else
    echo "ERROR: Integrity check FAILED"
    exit 1
fi

echo "Deployment complete: $DEPLOY_DIR"
'''
        deploy_script_path = os.path.join(output_dir, "deploy.sh")
        with open(deploy_script_path, "w") as f:
            f.write(deploy_script)
        os.chmod(deploy_script_path, 0o755)
        files_to_include.append("deploy.sh")

        logger.info(f"Packaged policy: {task} v{version} -> {output_dir}")
        return {
            "output_dir": output_dir,
            "manifest": manifest,
            "files": files_to_include,
            "version": version,
        }

    def validate_package(self, package_dir: str) -> dict:
        """Validate a deployment package for completeness and integrity."""
        issues = []
        warnings = []

        # Check manifest
        manifest_path = os.path.join(package_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            issues.append("Missing manifest.json")
            return {"valid": False, "issues": issues, "warnings": warnings}

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Validate required fields
        required_fields = ["package_version", "policy", "metadata"]
        for field in required_fields:
            if field not in manifest:
                issues.append(f"Missing required field in manifest: {field}")

        # Check policy file exists
        policy_file = manifest.get("policy", {}).get("file", "")
        policy_path = os.path.join(package_dir, policy_file)
        if not os.path.exists(policy_path):
            issues.append(f"Policy file missing: {policy_file}")
        else:
            actual_size = os.path.getsize(policy_path)
            expected_size = manifest.get("policy", {}).get("size_bytes", 0)
            if expected_size > 0 and actual_size != expected_size:
                issues.append(f"Policy size mismatch: expected {expected_size}, got {actual_size}")

        # Check checksums
        checksum_path = os.path.join(package_dir, "checksums.sha256")
        if os.path.exists(checksum_path):
            with open(checksum_path) as f:
                for line in f:
                    parts = line.strip().split("  ")
                    if len(parts) == 2:
                        expected_hash, filename = parts
                        filepath = os.path.join(package_dir, filename)
                        if os.path.exists(filepath):
                            actual_hash = hashlib.sha256(
                                open(filepath, "rb").read()
                            ).hexdigest()
                            if actual_hash != expected_hash:
                                issues.append(f"Checksum mismatch for {filename}")
                        else:
                            issues.append(f"File referenced in checksums missing: {filename}")
        else:
            warnings.append("No checksums.sha256 file found")

        # Check deploy script
        if not os.path.exists(os.path.join(package_dir, "deploy.sh")):
            warnings.append("No deploy.sh script found")

        # Check metadata completeness
        meta = manifest.get("metadata", {})
        if not meta.get("version"):
            warnings.append("No version in metadata")
        if not meta.get("robot"):
            warnings.append("No robot type in metadata")

        valid = len(issues) == 0

        result = {
            "valid": valid,
            "issues": issues,
            "warnings": warnings,
            "manifest": manifest,
            "files_found": os.listdir(package_dir),
        }
        logger.info(f"Package validation: {'PASS' if valid else 'FAIL'} "
                     f"({len(issues)} issues, {len(warnings)} warnings)")
        return result

    def sign_package(self, package_dir: str) -> dict:
        """Sign package with SHA-256 checksums for integrity verification."""
        checksums = {}
        files_signed = []

        for filename in os.listdir(package_dir):
            filepath = os.path.join(package_dir, filename)
            if os.path.isfile(filepath) and filename != "checksums.sha256":
                with open(filepath, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                checksums[filename] = file_hash
                files_signed.append(filename)

        # Write checksums file
        checksum_path = os.path.join(package_dir, "checksums.sha256")
        with open(checksum_path, "w") as f:
            for filename, hash_val in sorted(checksums.items()):
                f.write(f"{hash_val}  {filename}\n")

        # Compute overall package hash
        all_hashes = "".join(sorted(checksums.values()))
        package_hash = hashlib.sha256(all_hashes.encode()).hexdigest()

        result = {
            "package_hash": package_hash,
            "files_signed": files_signed,
            "checksums": checksums,
            "checksum_file": checksum_path,
        }
        logger.info(f"Signed package: {len(files_signed)} files, hash={package_hash[:16]}...")
        return result

    def generate_release_notes(self, version: str, changes: list = None,
                                test_results: dict = None,
                                previous_version: str = None) -> str:
        """Generate formatted release notes for a policy deployment."""
        changes = changes or []
        test_results = test_results or {}

        lines = [
            f"# Release Notes - v{version}",
            "",
        ]

        if previous_version:
            lines.append(f"**Previous version:** v{previous_version}")
            lines.append("")

        lines.append(f"**Release date:** {time.strftime('%Y-%m-%d')}")
        lines.append("")

        if changes:
            lines.append("## Changes")
            lines.append("")
            for change in changes:
                lines.append(f"- {change}")
            lines.append("")

        if test_results:
            lines.append("## Test Results")
            lines.append("")

            if "safety" in test_results:
                sf = test_results["safety"]
                status = "PASS" if sf.get("overall_pass", False) else "FAIL"
                lines.append(f"### Safety Tests: {status}")
                lines.append(f"- Tests run: {sf.get('tests_run', 0)}")
                lines.append(f"- Passed: {sf.get('passed', 0)}")
                lines.append(f"- Failed: {sf.get('failed', 0)}")
                lines.append("")

            if "performance" in test_results:
                perf = test_results["performance"]
                lines.append("### Performance")
                lines.append(f"- Success rate: {perf.get('success_rate', 0):.1%}")
                lines.append(f"- Mean reward: {perf.get('mean_reward', 0):.2f}")
                lines.append(f"- Mean episode length: {perf.get('mean_length', 0):.0f}")
                lines.append("")

            if "sim_to_real" in test_results:
                s2r = test_results["sim_to_real"]
                lines.append("### Sim-to-Real Transfer")
                lines.append(f"- Reality gap quality: {s2r.get('quality', 'unknown')}")
                lines.append(f"- Transfer validation: "
                             f"{'PASS' if s2r.get('passed', False) else 'FAIL'}")
                lines.append("")

        lines.extend([
            "## Deployment",
            "",
            "```bash",
            "# Deploy to robot",
            f"./deploy.sh",
            "```",
            "",
            "---",
            f"*Generated by agent-stack v{version}*",
        ])

        report = "\n".join(lines)
        logger.info(f"Generated release notes for v{version}")
        return report
