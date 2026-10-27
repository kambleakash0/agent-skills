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
  - A chunk that runs past its timeout is interrupted, so the kernel is free
    again for the next call.
  - Tools run in worker threads. A registry lock guards _kernels, and each
    session's lock is held for all of execute() and for kernel starts, so
    concurrent calls run one at a time and never read each other's iopub
    messages. interrupt() never takes that lock; restart() and shutdown() kill
    the kernel of a running chunk instead of waiting for it, which makes that
    execute() fail with "Kernel died during execution", and take the lock
    ahead of queued calls, which then run on the restarted kernel (or fail
    with "Kernel was shut down").
"""
from __future__ import annotations

import contextlib
import logging
import os
import queue
import re
import signal
import sys
import threading
import time

from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel
from traitlets.log import get_logger as _jupyter_global_logger

logger = logging.getLogger(__name__)

# Seconds a timed-out chunk gets to stop after the kernel is interrupted.
_INTERRUPT_GRACE = 5.0

_NOT_RUNNING = "Kernel is not running (its process has exited); execute_cell will start a new one"

# Start failures whose KernelError message already says what is wrong: missing
# kernelspec, missing or non-executable kernel binary.
_EXPECTED_START_ERRORS = (NoSuchKernel, FileNotFoundError, PermissionError)


class KernelError(Exception):
    pass


class _SessionRetired(KernelError):
    """The session was shut down, or its kernel failed to start, before this call got the lock."""


class _QuietExpectedStartFailure(logging.Filter):
    """
    Drops jupyter_client's records about an expected start failure: the traceback
    start_kernel() logs, and the launcher's "Failed to run command" dump. The
    launcher logs from inside its except block, so the failure is sys.exc_info().
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else sys.exc_info()[1]
        return not isinstance(exc, _EXPECTED_START_ERRORS)


@contextlib.contextmanager
def _quiet_expected_start_failures(km: KernelManager):
    """Filter jupyter_client's loggers for one start or restart call; other diagnostics are untouched."""
    # km.log and the launcher's global logger may be LoggerAdapters; filters go on the Logger.
    loggers = {getattr(lg, "logger", lg) for lg in (km.log, _jupyter_global_logger())}
    quiet = _QuietExpectedStartFailure()
    for lg in loggers:
        lg.addFilter(quiet)
    try:
        yield
    finally:
        for lg in loggers:
            lg.removeFilter(quiet)


class _KernelSession:
    def __init__(self, kernel_name: str = "ir", cwd: str | None = None, file_path: str | None = None):
        self.kernel_name = kernel_name
        # Working directory for the kernel process (the .rmd file's folder).
        self.cwd = cwd
        # Registry key, so a failed start can drop this session from _kernels.
        self.file_path = file_path
        self.km: KernelManager | None = None
        self.kc = None
        # Held for all of execute() and for start/restart/shutdown. Re-entrant
        # because execute() restarts a dead kernel itself.
        self._lock = threading.RLock()
        # True while execute() waits for a chunk's outputs (see _exclusive).
        self._executing = False
        # restart() / shutdown() calls waiting for the lock, changed under _registry_lock;
        # execute() lets them take it first (see _acquire_for_execute).
        self._preempting = 0
        # Why this session can't be used any more (shut down, or failed start), else None.
        self._retired: str | None = None

    def start(self) -> None:
        """
        Start the kernel unless it is running. On failure, raise KernelError after
        releasing everything and dropping this session from the registry.
        """
        if self._retired is None and self.is_alive():
            return
        with self._lock:
            if self._retired is not None:
                raise _SessionRetired(self._retired)
            if self.is_alive():
                return
            # Release a dead kernel's channels and connection file before starting a new one.
            self._release()
            try:
                self.km = KernelManager(kernel_name=self.kernel_name)
                with _quiet_expected_start_failures(self.km):
                    # restart_kernel() reuses these launch args, so cwd survives restarts.
                    self.km.start_kernel(cwd=self.cwd)
                self.kc = self.km.client()
                self.kc.start_channels()
                self.kc.wait_for_ready(timeout=30)
            except Exception as e:
                message = str(e) if isinstance(e, NoSuchKernel) else f"Kernel failed to start: {e}"
                raise self._abandon(message) from e

    def is_alive(self) -> bool:
        km = self.km
        try:
            return km is not None and km.is_alive()
        except Exception:
            # A concurrent restart or shutdown can tear the manager down mid-call.
            return False

    def interrupt(self) -> None:
        """Interrupt the running chunk. Never waits for the session lock: stopping a running execute() is the point."""
        km = self.km
        if km is None:
            raise KernelError("No kernel to interrupt")
        # Signalling a dead process "succeeds", so check first.
        if not self.is_alive():
            raise KernelError(_NOT_RUNNING)
        try:
            km.interrupt_kernel()
        except Exception as e:
            raise KernelError(f"Kernel interrupt failed: {e}") from e

    def restart(self) -> None:
        """
        Restart the kernel with its original launch args (cwd included). A running
        chunk is killed rather than waited for, and queued chunks run on the
        restarted kernel (see _exclusive). A failed restart drops the session, like
        a failed start.
        """
        with self._exclusive():
            if self.km is None:
                raise KernelError("No kernel to restart")
            try:
                # Relaunches with the original start_kernel() args, including cwd.
                with _quiet_expected_start_failures(self.km):
                    self.km.restart_kernel(now=True)
                if self.kc is not None:
                    self.kc.stop_channels()
                self.kc = self.km.client()
                self.kc.start_channels()
            except Exception as e:
                raise self._abandon(f"Kernel failed to restart: {e}") from e
            try:
                self.kc.wait_for_ready(timeout=30)
            except Exception as e:
                raise self._abandon(f"Kernel failed to restart cleanly: {e}") from e

    def shutdown(self) -> None:
        """
        Shut the kernel down for good and drop this session from the registry;
        later calls on it raise KernelError. A running chunk is killed rather than
        waited for (see _exclusive).
        """
        # Retire first, so an execute() queued on the lock fails instead of starting a new kernel.
        _forget(self, "Kernel was shut down")
        with self._exclusive():
            self._release()

    def execute(self, code: str, timeout: float = 60.0) -> list[dict]:
        """
        Execute code and return a list of captured output dicts. Holds the
        session lock throughout, so concurrent calls on one kernel run one at a time.
        """
        self._acquire_for_execute()
        try:
            # Starts a kernel that died since the last call; a failed start unregisters the session.
            self.start()
            kc = self.kc
            assert kc is not None
            msg_id = kc.execute(code)
            # While set, restart() and shutdown() kill this chunk instead of waiting for it.
            self._executing = True
            try:
                return self._collect_outputs(kc, msg_id, timeout)
            finally:
                self._executing = False
        finally:
            self._lock.release()

    def _acquire_for_execute(self) -> None:
        """
        Take the session lock for execute(), letting a restart() or shutdown() that
        is waiting for it go first. Otherwise a queued execute() could take the lock
        the moment the running chunk is killed, start a new kernel for its own
        chunk, and be killed in turn.
        """
        while True:
            self._lock.acquire()
            if not self._preempting:
                return
            self._lock.release()
            time.sleep(0.05)

    def _collect_outputs(self, kc, msg_id: str, timeout: float) -> list[dict]:
        """Read iopub until the request with msg_id goes idle, collecting its outputs."""
        outputs: list[dict] = []
        deadline = time.time() + timeout
        # Set by the chunk's first message other than a status (execute_input, or an
        # output). A kernel can ignore an interrupt that arrives before then (ipykernel
        # does), so a chunk that times out before it starts is interrupted once it
        # does (or, failing that, _INTERRUPT_GRACE seconds after the timeout).
        started = False

        while True:
            now = time.time()
            if now >= deadline and (started or now >= deadline + _INTERRUPT_GRACE):
                raise self._stop_timed_out(kc, msg_id, timeout)
            remaining = (deadline if now < deadline else deadline + _INTERRUPT_GRACE) - now
            try:
                msg = kc.get_iopub_msg(timeout=min(remaining, 1.0))
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
            started = started or mtype != "status"
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

    def _stop_timed_out(self, kc, msg_id: str, timeout: float) -> KernelError:
        """
        Interrupt a chunk that ran past its timeout, then wait up to _INTERRUPT_GRACE
        seconds for its idle status so the kernel is free for the next call.
        Returns the KernelError to raise.
        """
        prefix = f"Execution timed out after {timeout}s"
        try:
            self.km.interrupt_kernel()
        except Exception as e:
            return KernelError(f"{prefix} and the kernel could not be interrupted ({e}); use restart_kernel to stop it")
        deadline = time.time() + _INTERRUPT_GRACE
        while (remaining := deadline - time.time()) > 0:
            try:
                msg = kc.get_iopub_msg(timeout=min(remaining, 0.5))
            except queue.Empty:
                if not self.is_alive():
                    return KernelError(f"{prefix}; the kernel died while being interrupted")
                continue
            if (
                msg.get("parent_header", {}).get("msg_id") == msg_id
                and msg["msg_type"] == "status"
                and msg["content"].get("execution_state") == "idle"
            ):
                return KernelError(
                    f"{prefix}; the cell was interrupted and the kernel is ready for the next one, with its state kept"
                )
        return KernelError(
            f"{prefix}; the kernel was interrupted but is still busy {_INTERRUPT_GRACE:g}s later. "
            "Use restart_kernel to stop it (in-memory state is lost)"
        )

    @contextlib.contextmanager
    def _exclusive(self):
        """
        Take the session lock for restart or shutdown, ahead of any execute() queued
        for it. While a chunk runs under it, kill the kernel instead of waiting for
        the chunk or its timeout: that execute() fails with "Kernel died during
        execution" within about a second and releases the lock. Only the running
        chunk is lost; queued chunks run afterwards. A kernel start in progress is
        waited for.
        """
        with _registry_lock:
            self._preempting += 1
        try:
            while not self._lock.acquire(timeout=0.2):
                if self._executing:
                    self._kill()
        finally:
            with _registry_lock:
                self._preempting -= 1
        try:
            yield
        finally:
            self._lock.release()

    def _kill(self) -> None:
        """Kill the kernel process. Only sends a signal, so it is safe without the lock."""
        km = self.km
        if km is None:
            return
        try:
            km.signal_kernel(getattr(signal, "SIGKILL", signal.SIGTERM))
        except Exception:
            pass

    def _abandon(self, message: str) -> KernelError:
        """
        Clean up after a failed start or restart: release the kernel, drop this
        session from the registry (kernel_state then reports "not started") and log
        one warning line. Returns the KernelError to raise.
        """
        self._release()
        _forget(self, message)
        logger.warning("%s (%s)", message, self.file_path)
        return KernelError(message)

    def _release(self) -> None:
        """Stop the client channels and the kernel, and free its connection file. Caller holds the lock."""
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


# Kernels keyed by .rmd file path. Every read and write holds _registry_lock,
# only for the dict access (never while a kernel starts or runs).
_kernels: dict[str, _KernelSession] = {}
_registry_lock = threading.Lock()


def get_or_start_kernel(file_path: str, kernel_name: str = "ir") -> _KernelSession:
    """
    Return an alive kernel session for this file, starting one if needed. The
    first registered session fixes the kernel name; later calls reuse it. Any
    startup failure raises KernelError and leaves no session registered.
    Concurrent calls start one kernel, not several.
    """
    while True:
        sess = get_kernel(file_path)
        if sess is None:
            # Start in the document's folder, like Jupyter, so relative paths in
            # chunks resolve against it rather than the server's working directory.
            cwd = os.path.dirname(os.path.abspath(file_path))
            new = _KernelSession(kernel_name=kernel_name, cwd=cwd, file_path=file_path)
            with _registry_lock:
                sess = _kernels.setdefault(file_path, new)
        try:
            sess.start()
        except _SessionRetired:
            # Shut down, or its start failed in another thread, while this call waited: look again.
            continue
        return sess


def get_kernel(file_path: str) -> _KernelSession | None:
    with _registry_lock:
        return _kernels.get(file_path)


def _forget(sess: _KernelSession, reason: str) -> None:
    """Retire sess and drop it from the registry if it is still the session registered for its file."""
    with _registry_lock:
        if sess._retired is None:
            sess._retired = reason
        if _kernels.get(sess.file_path) is sess:
            del _kernels[sess.file_path]


def restart_kernel(file_path: str) -> None:
    sess = get_kernel(file_path)
    if sess is None:
        raise KernelError(f"No kernel running for {file_path}")
    sess.restart()


def interrupt_kernel(file_path: str) -> None:
    sess = get_kernel(file_path)
    if sess is None:
        raise KernelError(f"No kernel running for {file_path}")
    sess.interrupt()


def shutdown_kernel(file_path: str) -> None:
    sess = get_kernel(file_path)
    if sess is not None:
        # Unregisters the session itself, and kills a running chunk rather than waiting for it.
        sess.shutdown()


def kernel_state(file_path: str) -> str:
    sess = get_kernel(file_path)
    if sess is None:
        return "not started"
    if sess.is_alive():
        return "alive"
    return "dead"


# IJulia names its kernelspecs after the Julia version, e.g. julia-1.11.
_JULIA_VERSIONED = re.compile(r"julia-(\d+(?:\.\d+)*)")


def julia_kernel_name() -> str:
    """
    Kernelspec name for julia chunks: "julia" or "julia-1" if installed, else the
    highest-versioned "julia-X.Y" (IJulia installs versioned names such as
    julia-1.11). Falls back to "julia-1", so a missing Julia kernel is reported
    under that name. Looks in the folders jupyter_client starts kernels from.
    """
    try:
        # ensure_native_kernel=False: no python3 lookup (and no "Native kernel ... is not available" warning).
        installed = set(KernelSpecManager(ensure_native_kernel=False).find_kernel_specs())
    except Exception:
        installed = set()
    for name in ("julia", "julia-1"):
        if name in installed:
            return name
    versioned = [
        (tuple(int(part) for part in m.group(1).split(".")), name)
        for name in installed
        if (m := _JULIA_VERSIONED.fullmatch(name))
    ]
    return max(versioned)[1] if versioned else "julia-1"


# ANSI CSI escape sequences (colors, cursor moves) that kernels put in
# tracebacks and stream output; they only cost tokens in returned text.
_ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def format_outputs(outputs: list[dict]) -> str:
    """Render captured outputs for inline return to the caller, minus ANSI escape codes. Errors include their traceback."""
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
            # As notebook-editor's get_outputs shows it: the error line, then the traceback.
            tb = o.get("traceback") or []
            lines = [f"[error] {o.get('ename','Error')}: {o.get('evalue','')}", *([tb] if isinstance(tb, str) else tb)]
            parts.append("\n".join(lines))
        else:
            parts.append(f"[{t}] {o}")
    text = "".join(parts) if all(p.startswith("[stream:") for p in parts) else "\n".join(parts)
    return _ANSI_CSI.sub("", text)
