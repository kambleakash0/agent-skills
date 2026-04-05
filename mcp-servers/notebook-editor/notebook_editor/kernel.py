"""
Python kernel execution for notebook cells using jupyter_client.

Design:
  - One kernel per notebook file path, cached in memory for the process lifetime
  - Lazy kernel start on first execute_cell
  - Blocking execution with a configurable timeout
  - Outputs captured from iopub channel and serialized back into nbformat output cells
  - Python kernel only (no multi-kernel support in v1)
"""
import queue
import time
from typing import Any

import nbformat
from jupyter_client import KernelManager


class KernelError(Exception):
    """Raised for kernel lifecycle or execution errors."""
    pass


class _KernelSession:
    """Wraps a jupyter_client KernelManager + BlockingKernelClient for one notebook."""

    def __init__(self, kernel_name: str = "python3"):
        self.kernel_name = kernel_name
        self.km: KernelManager | None = None
        self.kc = None

    def start(self) -> None:
        if self.km is not None and self.km.is_alive():
            return
        self.km = KernelManager(kernel_name=self.kernel_name)
        self.km.start_kernel()
        self.kc = self.km.client()
        self.kc.start_channels()
        # Wait for the kernel to be ready
        try:
            self.kc.wait_for_ready(timeout=30)
        except RuntimeError as e:
            self.shutdown()
            raise KernelError(f"Kernel failed to start: {e}") from e

    def is_alive(self) -> bool:
        return self.km is not None and self.km.is_alive()

    def interrupt(self) -> None:
        if self.km is None:
            raise KernelError("No kernel to interrupt")
        self.km.interrupt_kernel()

    def restart(self) -> None:
        if self.km is None:
            raise KernelError("No kernel to restart")
        self.km.restart_kernel(now=True)
        # Re-establish client channels after restart
        if self.kc is not None:
            self.kc.stop_channels()
        self.kc = self.km.client()
        self.kc.start_channels()
        try:
            self.kc.wait_for_ready(timeout=30)
        except RuntimeError as e:
            raise KernelError(f"Kernel failed to restart cleanly: {e}") from e

    def shutdown(self) -> None:
        if self.kc is not None:
            try:
                self.kc.stop_channels()
            except Exception:
                pass
            self.kc = None
        if self.km is not None and self.km.is_alive():
            try:
                self.km.shutdown_kernel(now=True)
            except Exception:
                pass
        self.km = None

    def execute(self, code: str, timeout: float = 60.0) -> tuple[list[dict], int | None]:
        """
        Execute a block of code and return (outputs, execution_count).
        outputs is a list of nbformat-compatible output dicts.
        """
        if not self.is_alive():
            self.start()
        assert self.kc is not None

        msg_id = self.kc.execute(code)
        outputs: list[dict] = []
        execution_count: int | None = None
        deadline = time.time() + timeout

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise KernelError(f"Execution timed out after {timeout}s")

            try:
                msg = self.kc.get_iopub_msg(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue

            parent = msg.get("parent_header", {})
            if parent.get("msg_id") != msg_id:
                continue

            msg_type = msg["msg_type"]
            content = msg["content"]

            if msg_type == "status" and content.get("execution_state") == "idle":
                break
            elif msg_type == "stream":
                outputs.append(
                    nbformat.v4.new_output(
                        output_type="stream",
                        name=content.get("name", "stdout"),
                        text=content.get("text", ""),
                    )
                )
            elif msg_type == "execute_result":
                execution_count = content.get("execution_count")
                outputs.append(
                    nbformat.v4.new_output(
                        output_type="execute_result",
                        data=content.get("data", {}),
                        metadata=content.get("metadata", {}),
                        execution_count=execution_count,
                    )
                )
            elif msg_type == "display_data":
                outputs.append(
                    nbformat.v4.new_output(
                        output_type="display_data",
                        data=content.get("data", {}),
                        metadata=content.get("metadata", {}),
                    )
                )
            elif msg_type == "error":
                outputs.append(
                    nbformat.v4.new_output(
                        output_type="error",
                        ename=content.get("ename", "Error"),
                        evalue=content.get("evalue", ""),
                        traceback=content.get("traceback", []),
                    )
                )
            elif msg_type == "execute_input":
                # execute_input carries the execution_count we'll stamp on the cell
                if execution_count is None:
                    execution_count = content.get("execution_count")

        return outputs, execution_count


# Module-level registry of kernels keyed by notebook file path
_kernels: dict[str, _KernelSession] = {}


def get_or_start_kernel(file_path: str) -> _KernelSession:
    sess = _kernels.get(file_path)
    if sess is None:
        sess = _KernelSession()
        _kernels[file_path] = sess
    if not sess.is_alive():
        sess.start()
    return sess


def get_kernel(file_path: str) -> _KernelSession | None:
    return _kernels.get(file_path)


def restart_kernel(file_path: str) -> None:
    sess = _kernels.get(file_path)
    if sess is None:
        raise KernelError(f"No kernel running for {file_path}")
    sess.restart()


def interrupt_kernel(file_path: str) -> None:
    sess = _kernels.get(file_path)
    if sess is None:
        raise KernelError(f"No kernel running for {file_path}")
    sess.interrupt()


def shutdown_kernel(file_path: str) -> None:
    sess = _kernels.pop(file_path, None)
    if sess is not None:
        sess.shutdown()


def kernel_state(file_path: str) -> str:
    sess = _kernels.get(file_path)
    if sess is None:
        return "not started"
    if sess.is_alive():
        return "alive"
    return "dead"
