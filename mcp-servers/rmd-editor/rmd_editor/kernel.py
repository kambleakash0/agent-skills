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

import queue
import time

from jupyter_client import KernelManager


class KernelError(Exception):
    pass


class _KernelSession:
    def __init__(self, kernel_name: str = "ir"):
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
        sess = _KernelSession(kernel_name=kernel_name)
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


def format_outputs(outputs: list[dict]) -> str:
    """Render captured outputs for inline return to the caller."""
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
    return "".join(parts) if all(p.startswith("[stream:") for p in parts) else "\n".join(parts)
