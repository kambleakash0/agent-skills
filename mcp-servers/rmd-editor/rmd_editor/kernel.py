"""
R kernel execution for .rmd chunks via jupyter_client + IRkernel.

Design:
  - One kernel per .rmd file path, cached in memory for the process lifetime.
  - Lazy kernel start on first execute_cell.
  - Default kernel_name is "ir" (the standard IRkernel identifier). Callers
    that want a different kernel (python3, julia-1.x) for polyglot .rmd
    documents can pass kernel_name explicitly, but the out-of-the-box story
    assumes R.
  - Unlike notebook-editor, outputs are NEVER written to the .rmd file —
    captured output is returned INLINE to the caller. R Markdown itself
    does not embed outputs (they're re-generated on render), so persisting
    them would drift from canonical .rmd semantics.
"""
from __future__ import annotations

import os
import queue
import re
import time

from jupyter_client import KernelManager
from jupyter_client.kernelspec import NoSuchKernel


class KernelError(Exception):
    pass


class _KernelSession:
    def __init__(self, kernel_name: str = "ir", cwd: str | None = None):
        self.kernel_name = kernel_name
        # Working directory for the kernel process (the .rmd file's folder).
        self.cwd = cwd
        self.km: KernelManager | None = None
        self.kc = None

    def start(self) -> None:
        if self.km is not None and self.km.is_alive():
            return
        # Release a dead kernel's channels and connection file before starting a new one.
        self.shutdown()
        try:
            self.km = KernelManager(kernel_name=self.kernel_name)
            # restart_kernel() reuses these launch args, so cwd survives restarts.
            self.km.start_kernel(cwd=self.cwd)
            self.kc = self.km.client()
            self.kc.start_channels()
            self.kc.wait_for_ready(timeout=30)
        except NoSuchKernel as e:
            self.shutdown()
            raise KernelError(str(e)) from e
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
            # Relaunches with the original start_kernel() args, including cwd.
            self.km.restart_kernel(now=True)
            if self.kc is not None:
                self.kc.stop_channels()
            self.kc = self.km.client()
            self.kc.start_channels()
        except Exception as e:
            raise KernelError(f"Kernel failed to restart: {e}") from e
        try:
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
                    # A kernel that failed to start (or died) can still own a
                    # connection file and sockets.
                    self.km.cleanup_resources()
            except Exception:
                pass
        self.km = None

    def execute(self, code: str, timeout: float = 60.0) -> list[dict]:
        """Execute code and return a list of captured output dicts."""
        if not self.is_alive():
            self.start()
        assert self.kc is not None

        msg_id = self.kc.execute(code)
        outputs: list[dict] = []
        deadline = time.time() + timeout

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise KernelError(f"Execution timed out after {timeout}s")
            try:
                msg = self.kc.get_iopub_msg(timeout=min(remaining, 1.0))
            except queue.Empty:
                # A dead kernel never sends "idle"; fail now instead of at the timeout.
                if not self.is_alive():
                    raise KernelError("Kernel died during execution")
                continue
            parent = msg.get("parent_header", {})
            if parent.get("msg_id") != msg_id:
                continue
            mtype = msg["msg_type"]
            content = msg["content"]
            if mtype == "status" and content.get("execution_state") == "idle":
                break
            elif mtype == "stream":
                outputs.append({
                    "output_type": "stream",
                    "name": content.get("name", "stdout"),
                    "text": content.get("text", ""),
                })
            elif mtype == "execute_result":
                outputs.append({
                    "output_type": "execute_result",
                    "data": content.get("data", {}),
                })
            elif mtype == "display_data":
                outputs.append({
                    "output_type": "display_data",
                    "data": content.get("data", {}),
                })
            elif mtype == "error":
                outputs.append({
                    "output_type": "error",
                    "ename": content.get("ename", "Error"),
                    "evalue": content.get("evalue", ""),
                    "traceback": content.get("traceback", []),
                })
        return outputs


_kernels: dict[str, _KernelSession] = {}


def get_or_start_kernel(file_path: str, kernel_name: str = "ir") -> _KernelSession:
    sess = _kernels.get(file_path)
    if sess is None:
        # Start in the document's folder, like Jupyter, so relative paths in
        # chunks resolve against it rather than the server's working directory.
        cwd = os.path.dirname(os.path.abspath(file_path))
        sess = _KernelSession(kernel_name=kernel_name, cwd=cwd)
        _kernels[file_path] = sess
    if not sess.is_alive():
        try:
            sess.start()
        except KernelError:
            # Drop the half-started session so kernel_state reports "not started".
            if _kernels.get(file_path) is sess:
                del _kernels[file_path]
            raise
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


# ANSI CSI escape sequences (colors, cursor moves) that kernels put in
# tracebacks and stream output; they only cost tokens in returned text.
_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def format_outputs(outputs: list[dict]) -> str:
    """Render captured outputs for inline return to the caller, minus ANSI escape codes."""
    if not outputs:
        return "(no output)"
    parts: list[str] = []
    for o in outputs:
        t = o.get("output_type")
        if t == "stream":
            parts.append(f"[stream:{o.get('name','stdout')}] {o.get('text','')}")
        elif t == "execute_result":
            data = o.get("data", {})
            text = data.get("text/plain", "")
            parts.append(f"[result] {text}")
        elif t == "display_data":
            data = o.get("data", {})
            if "image/png" in data:
                parts.append("[display] <image/png>")
            elif "text/plain" in data:
                parts.append(f"[display] {data['text/plain']}")
            else:
                parts.append(f"[display] <{', '.join(data.keys())}>")
        elif t == "error":
            parts.append(f"[error] {o.get('ename','Error')}: {o.get('evalue','')}")
        else:
            parts.append(f"[{t}] {o}")
    text = "".join(parts) if all(p.startswith("[stream:") for p in parts) else "\n".join(parts)
    return _ANSI_CSI.sub("", text)
