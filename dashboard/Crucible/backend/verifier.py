import subprocess
import os
import uuid
import time
import hashlib
from .models import ExecutionProof, ExecutionStatus

class Verifier:
    def __init__(self, sandbox_dir: str = "/tmp/crucible_sandbox"):
        self.sandbox_dir = sandbox_dir
        if not os.path.exists(self.sandbox_dir):
            os.makedirs(self.sandbox_dir)

    def verify_code(self, code: str) -> ExecutionProof:
        """
        Executes the submitted code in a temporary file and returns an ExecutionProof.
        For the MVP, we are assuming it's a Python script.
        """
        file_id = str(uuid.uuid4())
        file_path = os.path.join(self.sandbox_dir, f"{file_id}.py")
        execution_hash = hashlib.sha256(code.encode()).hexdigest()

        with open(file_path, "w") as f:
            f.write(code)

        start_time = time.time()
        try:
            # Rule 5: Hardened subprocess execution. 
            # No shell=True, 5-second timeout, capture all output.
            result = subprocess.run(
                ["python3", file_path],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            runtime_ms = (time.time() - start_time) * 1000
            
            status = ExecutionStatus.SUCCESS if result.returncode == 0 else ExecutionStatus.FAIL
            return ExecutionProof(
                execution_hash=execution_hash,
                status=status,
                runtime_ms=runtime_ms,
                exit_code=result.returncode,
                output_log=result.stdout + result.stderr
            )
        except subprocess.TimeoutExpired:
            return ExecutionProof(
                execution_hash=execution_hash,
                status=ExecutionStatus.FAIL,
                runtime_ms=5000.0,
                exit_code=124, # Standard timeout exit code
                output_log="Execution timed out after 5.0 seconds."
            )
        except Exception as e:
            return ExecutionProof(
                execution_hash=execution_hash,
                status=ExecutionStatus.FAIL,
                runtime_ms=0.0,
                exit_code=1,
                output_log=f"Internal Verifier Error: {str(e)}"
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
