"""Bounded optional cleanup and final exit for the standalone frozen app."""
import logging
import os
import sys
import threading
import subprocess

_reader_lock=threading.Lock()
_readers=set()
_readers_closing=False


def run_owned_reader(args, **kwargs):
    """Track only our read-only DB helpers, so they cannot outlive the UI."""
    timeout=kwargs.pop('timeout',90)
    kwargs.pop('capture_output',None)
    with _reader_lock:
        if _readers_closing:raise RuntimeError('Server is closing')
        process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
        _readers.add(process)
    try:
        stdout,stderr=process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    except BaseException:
        if process.poll() is None:process.kill()
        process.communicate(timeout=2)
        raise
    finally:
        with _reader_lock:_readers.discard(process)


def close_owned_readers():
    global _readers_closing
    with _reader_lock:
        _readers_closing=True;active=tuple(_readers)
    for process in active:
        if process.poll() is not None:continue
        process.terminate()
        try:process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=1)


def cleanup_step(label, action, log):
    try:
        return action()
    except Exception as exc:
        try:log(f'Shutdown: {label} failed', exc)
        except Exception:pass


def bounded_cleanup(label, action, log, timeout=1.0):
    worker=threading.Thread(target=lambda:cleanup_step(label,action,log),
                            name='server16-shutdown-'+label,daemon=True)
    worker.start();worker.join(timeout)
    if worker.is_alive():log(f'Shutdown: {label} exceeded {timeout:.1f}s; continuing local cleanup')


def finish_frozen_process():
    # Only the standalone EXE owns this process. After explicit app cleanup,
    # avoid waiting indefinitely for native/CLR finalizers or library threads.
    # Never terminate FIFA, the bootloader parent or another Server instance.
    if not getattr(sys,'frozen',False):return
    logging.shutdown()
    for stream in (sys.stdout,sys.stderr):
        try:
            if stream is not None:stream.flush()
        except (OSError,ValueError):pass
    os._exit(0)
