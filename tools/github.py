# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
GitHub CLI (gh) wrapper for repository, issue, release, and PR management.
"""

import os
import subprocess
import json
import shlex
import base64
from tools.bash import RequiresApprovalError


def _gh(args: str) -> dict:
    """
    Run a GitHub CLI command.

    Args:
        args: Arguments to pass to 'gh' (e.g. "repo list").

    Returns:
        Dict with stdout, stderr, returncode.
    """
    try:
        result = subprocess.run(
            f"gh {args}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "gh command timed out",
            "returncode": -1,
        }


def clone_repo(repo_name: str, local_path: str) -> bool:
    """
    Clone a GitHub repository.

    Args:
        repo_name: Repository in "owner/repo" format.
        local_path: Local directory to clone into.

    Returns:
        True if successful.
    """
    result = _gh(f"repo clone {shlex.quote(repo_name)} {shlex.quote(local_path)}")
    return result["returncode"] == 0


def pull_latest(local_path: str) -> bool:
    """
    Pull latest changes in a local repository.

    Args:
        local_path: Path to the local git repository.

    Returns:
        True if successful.
    """
    result = subprocess.run(
        f"git -C {shlex.quote(local_path)} pull",
        shell=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode == 0


def read_file(repo: str, path: str) -> str:
    """
    Read a file's contents from a GitHub repository.

    Args:
        repo: Repository in "owner/repo" format.
        path: File path within the repository.

    Returns:
        Decoded file content string.
    """
    result = _gh(f"api repos/{repo}/contents/{path}")
    if result["returncode"] != 0:
        raise RuntimeError(f"Failed to read {path} from {repo}: {result['stderr']}")

    data = json.loads(result["stdout"])
    content_b64 = data.get("content", "")
    return base64.b64decode(content_b64).decode("utf-8")


def push_results(repo: str, results_path: str, commit_msg: str) -> bool:
    """
    Add, commit, and push results to a repository.

    Args:
        repo: Not used directly; operates on local clone at results_path parent.
        results_path: Path to the results file/directory to push.
        commit_msg: Commit message.

    Returns:
        True if successful.
    """
    repo_dir = os.path.dirname(results_path)
    escaped_dir = shlex.quote(repo_dir)
    escaped_msg = shlex.quote(commit_msg)

    result = subprocess.run(
        f"git -C {escaped_dir} add -A && "
        f"git -C {escaped_dir} commit -m {escaped_msg} && "
        f"git -C {escaped_dir} push",
        shell=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0


def create_issue(repo: str, title: str, body: str, labels: list = None) -> int:
    """
    Create a new GitHub issue.

    Args:
        repo: Repository in "owner/repo" format.
        title: Issue title.
        body: Issue body text.
        labels: Optional list of label strings.

    Returns:
        Issue number.
    """
    cmd = f"issue create -R {shlex.quote(repo)} --title {shlex.quote(title)} --body {shlex.quote(body)}"
    if labels:
        label_str = ",".join(labels)
        cmd += f" --label {shlex.quote(label_str)}"

    result = _gh(cmd)
    if result["returncode"] != 0:
        raise RuntimeError(f"Failed to create issue: {result['stderr']}")

    # gh issue create outputs the URL; extract issue number from it
    url = result["stdout"].strip()
    issue_number = int(url.rstrip("/").split("/")[-1])
    return issue_number


def close_issue(repo: str, issue_number: int, comment: str = "") -> bool:
    """
    Close a GitHub issue.

    Args:
        repo: Repository in "owner/repo" format.
        issue_number: Issue number to close.
        comment: Optional closing comment.

    Returns:
        True if successful.
    """
    if comment:
        _gh(f"issue comment {issue_number} -R {shlex.quote(repo)} --body {shlex.quote(comment)}")

    result = _gh(f"issue close {issue_number} -R {shlex.quote(repo)}")
    return result["returncode"] == 0


def list_issues(repo: str, state: str = "open") -> list:
    """
    List issues in a repository.

    Args:
        repo: Repository in "owner/repo" format.
        state: Issue state filter ("open", "closed", "all").

    Returns:
        List of issue dicts.
    """
    result = _gh(
        f"issue list -R {shlex.quote(repo)} --state {state} "
        f"--json number,title,state,labels,assignees,createdAt"
    )
    if result["returncode"] != 0:
        return []

    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        return []


def update_file(repo: str, path: str, content: str, commit_msg: str) -> bool:
    """
    Update a file in a GitHub repository via the API.

    Args:
        repo: Repository in "owner/repo" format.
        path: File path within the repository.
        content: New file content.
        commit_msg: Commit message.

    Returns:
        True if successful.
    """
    # First get the current file SHA
    get_result = _gh(f"api repos/{repo}/contents/{path}")
    if get_result["returncode"] != 0:
        sha = None
    else:
        data = json.loads(get_result["stdout"])
        sha = data.get("sha")

    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": commit_msg,
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    payload_json = json.dumps(payload)
    result = _gh(
        f"api repos/{repo}/contents/{path} "
        f"-X PUT --input - <<< {shlex.quote(payload_json)}"
    )
    return result["returncode"] == 0


def push_to_main(repo: str, files: list, commit_msg: str) -> bool:
    """
    Push files directly to the main branch. Requires approval.

    Raises:
        RequiresApprovalError: Always, since pushing to main is destructive.
    """
    raise RequiresApprovalError(f"git push to main on {repo}")


def create_release(repo: str, tag: str, name: str, notes: str) -> str:
    """
    Create a GitHub release. Requires approval.

    Raises:
        RequiresApprovalError: Always, since creating releases is destructive.
    """
    raise RequiresApprovalError(f"create release {tag} on {repo}")


def merge_pr(repo: str, pr_number: int) -> bool:
    """
    Merge a pull request. Requires approval.

    Raises:
        RequiresApprovalError: Always, since merging PRs is destructive.
    """
    raise RequiresApprovalError(f"merge PR #{pr_number} on {repo}")


def delete_branch(repo: str, branch: str) -> bool:
    """
    Delete a branch from a repository. Requires approval.

    Raises:
        RequiresApprovalError: Always, since deleting branches is destructive.
    """
    raise RequiresApprovalError(f"delete branch {branch} on {repo}")
