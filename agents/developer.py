#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Developer agent for code generation, debugging, and refactoring."""

import os
import sys
import ast
import tempfile
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent


class DeveloperAgent(BaseAgent):
    """Agent for code generation, debugging, fixing errors, and refactoring."""

    task_type = "code_generation"

    KNOWLEDGE_DOMAINS = [
        "Isaac Sim 5.1 API",
        "cuRobo 0.7.7 API",
        "ROS2 Jazzy API",
        "Python best practices",
    ]

    def __init__(self):
        super().__init__(self.task_type)
        self._SKILL_REGISTRY = {
            "generate_code": self.generate_code,
            "fix_error": self.fix_error,
            "refactor": self.refactor,
        }

    def _validate_python(self, code: str) -> tuple[bool, str]:
        """Validate Python syntax. Returns (valid, error_message)."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"

    def _check_imports(self, code: str) -> tuple[bool, str]:
        """Run basic import check by executing the code in a subprocess with --check flag."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                result = subprocess.run(
                    [sys.executable, "-c", f"import ast; ast.parse(open('{f.name}').read()); print('OK')"],
                    capture_output=True, text=True, timeout=10,
                )
                return result.returncode == 0, result.stderr
            except subprocess.TimeoutExpired:
                return False, "Import check timed out"
            finally:
                os.unlink(f.name)

    def generate_code(self, task: str, context: str = "", output_path: str = None) -> str:
        """Generate code for a robotics task.

        Queries the model with task + knowledge context.
        Validates Python syntax before saving.
        Auto-retries up to 3x on syntax errors.
        """
        knowledge = self.load_knowledge(self.task_type)

        prompt = f"""You are an expert robotics software engineer.

Knowledge context:
{knowledge}

Additional context:
{context}

Task: {task}

Write clean, production-quality Python code. Include necessary imports.
Only output the code, no explanations or markdown fences."""

        model_info = self.get_model_info()
        last_error = ""

        for attempt in range(1, 4):
            self.logger.info(f"Code generation attempt {attempt}/3")

            if last_error:
                prompt += f"\n\nPrevious attempt had syntax error: {last_error}\nFix the error and regenerate."

            try:
                code = self.query_with_retry(prompt)
            except RuntimeError as e:
                self.log_task(task=task, result=str(e), model=model_info["model"], success=False, retries=attempt)
                raise

            # Strip markdown fences if model included them
            code = code.strip()
            if code.startswith("```python"):
                code = code[len("```python"):].strip()
            if code.startswith("```"):
                code = code[3:].strip()
            if code.endswith("```"):
                code = code[:-3].strip()

            valid, error = self._validate_python(code)
            if valid:
                if output_path:
                    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                    with open(output_path, "w") as f:
                        f.write(code)
                    self.logger.info(f"Code saved to {output_path}")

                self.log_task(task=task, result=f"Generated {len(code)} chars",
                              model=model_info["model"], success=True, retries=attempt - 1)
                self.log_activity("code_generation", f"Generated code: {task[:80]}")
                return code
            else:
                last_error = error
                self.logger.warning(f"Attempt {attempt} syntax error: {error}")

        self.log_task(task=task, result=f"Failed after 3 attempts: {last_error}",
                      model=model_info["model"], success=False, retries=3)
        raise RuntimeError(f"Code generation failed after 3 attempts. Last error: {last_error}")

    def fix_error(self, error_log: str, file_path: str) -> str:
        """Analyze an error and generate a fix for the specified file.

        Reads the file, sends it with the error to the model,
        validates the fix, and saves if valid.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path) as f:
            original_code = f.read()

        knowledge = self.load_knowledge(self.task_type)
        model_info = self.get_model_info()

        prompt = f"""You are an expert robotics software engineer debugging code.

Knowledge context:
{knowledge}

File: {file_path}
```python
{original_code}
```

Error log:
```
{error_log}
```

Fix the error. Output ONLY the complete corrected file contents, no explanations."""

        for attempt in range(1, 4):
            try:
                fixed_code = self.query_with_retry(prompt)
            except RuntimeError as e:
                self.log_task(task=f"fix_error:{file_path}", result=str(e),
                              model=model_info["model"], success=False, retries=attempt)
                raise

            fixed_code = fixed_code.strip()
            if fixed_code.startswith("```python"):
                fixed_code = fixed_code[len("```python"):].strip()
            if fixed_code.startswith("```"):
                fixed_code = fixed_code[3:].strip()
            if fixed_code.endswith("```"):
                fixed_code = fixed_code[:-3].strip()

            valid, error = self._validate_python(fixed_code)
            if valid:
                with open(file_path, "w") as f:
                    f.write(fixed_code)
                self.logger.info(f"Fix applied to {file_path}")
                self.log_task(task=f"fix_error:{file_path}", result="Fix applied",
                              model=model_info["model"], success=True, retries=attempt - 1)
                self.log_activity("bug_fix", f"Fixed error in {file_path}")
                return fixed_code
            else:
                self.logger.warning(f"Fix attempt {attempt} has syntax error: {error}")
                prompt += f"\n\nYour fix had a syntax error: {error}. Try again."

        self.log_task(task=f"fix_error:{file_path}", result="Failed to fix after 3 attempts",
                      model=model_info["model"], success=False, retries=3)
        raise RuntimeError(f"Failed to fix {file_path} after 3 attempts")

    def refactor(self, file_path: str, instructions: str) -> str:
        """Refactor code according to instructions.

        Reads the file, applies refactoring via model, validates, and saves.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path) as f:
            original_code = f.read()

        model_info = self.get_model_info()

        prompt = f"""You are an expert software engineer refactoring code.

File: {file_path}
```python
{original_code}
```

Refactoring instructions: {instructions}

Output ONLY the complete refactored file, no explanations."""

        try:
            refactored = self.query_with_retry(prompt)
        except RuntimeError as e:
            self.log_task(task=f"refactor:{file_path}", result=str(e),
                          model=model_info["model"], success=False)
            raise

        refactored = refactored.strip()
        if refactored.startswith("```python"):
            refactored = refactored[len("```python"):].strip()
        if refactored.startswith("```"):
            refactored = refactored[3:].strip()
        if refactored.endswith("```"):
            refactored = refactored[:-3].strip()

        valid, error = self._validate_python(refactored)
        if not valid:
            self.log_task(task=f"refactor:{file_path}", result=f"Syntax error: {error}",
                          model=model_info["model"], success=False)
            raise RuntimeError(f"Refactored code has syntax error: {error}")

        with open(file_path, "w") as f:
            f.write(refactored)

        self.log_task(task=f"refactor:{file_path}", result="Refactored successfully",
                      model=model_info["model"], success=True)
        self.log_activity("refactor", f"Refactored {file_path}: {instructions[:60]}")
        return refactored
