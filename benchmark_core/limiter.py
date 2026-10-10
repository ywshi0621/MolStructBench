"""Cross-process provider concurrency, outside every scientific sandbox."""
import contextlib
import fcntl
import os
import pathlib
import time

@contextlib.contextmanager
def provider_slot(kind='solver', slots=9, cancelled=None):
    root=pathlib.Path(os.environ.get('MOLSTRUCTBENCH_GLOBAL_LIMIT_DIR',os.environ.get('SCIBENCH_GLOBAL_LIMIT_DIR','/tmp/molstructbench-provider-slots')))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle=None
    while handle is None:
        if cancelled and cancelled():raise TimeoutError('Sample cancelled')
        for i in range(slots):
            f=(root/(kind+'-'+str(i))).open('a')
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:f.close()
            else:handle=f;break
        if handle is None:time.sleep(.1)
    try:yield
    finally:
        fcntl.flock(handle,fcntl.LOCK_UN)
        handle.close()
