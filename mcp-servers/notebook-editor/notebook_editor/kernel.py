"""
Kernel execution for notebook cells using jupyter_client.

Design:
  - One kernel per notebook file path, cached in memory for the process lifetime
  - Lazy kernel start on first execute_cell
  - Kernel selection is driven by the notebook's metadata.kernelspec.name
    (falls back to "python3" if unreadable). Works with any Jupyter kernel
    installed on the host (IRkernel for R, IJulia for Julia, etc.).
  - The kernel process starts in the notebook's folder, like Jupyter
  - Blocking execution with a configurable timeout
  - Outputs captured from iopub channel and serialized back into nbformat output cells
"""
import os
import queue
import time
from typing import Any

import nbformat
from jupyter_client import KernelManager
from jupyter_client.kernelspec import NoSuchKernel


class KernelError(Exception):
    """Raised for kernel lifecycle or execution errors."""
    pass


class _KernelSession:
    """Wraps a jupyter_client KernelManager + BlockingKernelClient for one notebook."""

    def __init__(self, kernel_name: str = "python3", cwd: str | None = None):
        self.kernel_name = kernel_name
        # Working directory for the kernel process (the notebook's folder, as in Jupyter)
        self.cwd = cwd
        self.km: KernelManager | None = None
        self.kc = None

    def start(self) -> None:
        if self.km is not None and self.km.is_alive():
            return
        # Release a dead kernel's channels and connection file before starting a new one
        self.shutdown()
        try:
            self.km = KernelManager(kernel_name=self.kernel_name)
            # Launch args (including cwd) are reused by km.restart_kernel()
            self.km.start_kernel(cwd=self.cwd)
        except NoSuchKernel as e:
            self.shutdown()
            raise KernelError(str(e)) from e
        except Exception as e:
            self.shutdown()
            raise KernelError(f"Kernel failed to start: {e}") from e
        # Wait for the kernel to be ready
        try:
            self.kc = self.km.client()
            self.kc.start_channels()
            self.kc.wait_for_ready(timeout=30)
        except Exception as e:
            self.shutdown()
            raise KernelError(f"Kernel failed to start: {e}") from e

    def is_alive(self) -> bool:
        return self.km is not None and self.km.is_alive()

    def interrupt(self) -> None:
        if self.km is None:
            raise KernelError("No kernel to interrupt")
        try:
            self.km.interrupt_kernel()
        except Exception as e:
            raise KernelError(f"Kernel interrupt failed: {e}") from e

    def restart(self) -> None:
        if self.km is None:
            raise KernelError("No kernel to restart")
        try:
            self.km.restart_kernel(now=True)
        except Exception as e:
            raise KernelError(f"Kernel failed to restart: {e}") from e
        # Re-establish client channels after restart
        if self.kc is not None:
            self.kc.stop_channels()
        try:
            self.kc = self.km.client()
            self.kc.start_channels()
            self.kc.wait_for_ready(timeout=30)
        except Exception as e:
            raise KernelError(f"Kernel failed to restart cleanly: {e}") from e

    def shutdown(self) -> None:
        if self.kc is not None:
            try:
                self.kc.stop_channels()
            except Exception:
                pass
            self.kc = None
        if self.km is not None:
            try:
                if self.km.is_alive():
                    self.km.shutdown_kernel(now=True)
                else:
                    # A kernel that failed to start or died leaves its connection file behind
                    self.km.cleanup_resources()
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
                # A dead kernel never sends "idle"; fail now instead of at the timeout
                if not self.is_alive():
                    raise KernelError("Kernel died during execution")
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


def get_or_start_kernel(file_path: str, kernel_name: str | None = None) -> _KernelSession:
    """
    Return an alive kernel session for this notebook, starting one if needed.

    If no session exists yet, the kernel_name is determined by (in priority order):
      1. The explicit `kernel_name` argument, if given.
      2. The notebook's `metadata.kernelspec.name` read from disk.
      3. Fallback to "python3".

    Once a session is registered for a file_path, subsequent calls reuse it and
    the kernel_name argument is ignored. Use shutdown_kernel() to reset.

    The kernel starts in the notebook's folder (as Jupyter does), so relative
    paths in cells resolve there. Any startup failure raises KernelError and
    leaves no session registered.
    """
    sess = _kernels.get(file_path)
    if sess is None:
        name = kernel_name or _read_notebook_kernel_name(file_path) or "python3"
        cwd = os.path.dirname(os.path.abspath(file_path))
        sess = _KernelSession(kernel_name=name, cwd=cwd)
        _kernels[file_path] = sess
    if not sess.is_alive():
        try:
            sess.start()
        except KernelError:
            # start() already cleaned up; drop the session so kernel_state reports "not started"
            if _kernels.get(file_path) is sess:
                del _kernels[file_path]
            raise
    return sess


def _read_notebook_kernel_name(file_path: str) -> str | None:
    """Best-effort read of metadata.kernelspec.name from a notebook file. Never raises."""
    try:
        nb = nbformat.read(file_path, as_version=4)
    except Exception:
        return None
    kspec = nb.metadata.get("kernelspec", {}) if nb.metadata else {}
    name = kspec.get("name")
    return name if isinstance(name, str) and name else None


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
