"""Tool boundary: Linux namespaces, mount allowlist, empty network, clean env."""
import argparse
import functools
import math
import json
import os
import re
import resource
import signal
import subprocess
import sys
from pathlib import Path

FORBIDDEN = re.compile(r'gold|private|mapping|answer|audit', re.I)

def inspect_workspace(workspace):
    root = Path(workspace).resolve(strict=True)
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('Symlinks are not allowed in initial workspace')
        if FORBIDDEN.search(str(p.relative_to(root))):
            raise ValueError('Forbidden filename in workspace')
    files = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if files != {'input/task.json'}:
        raise ValueError('Only the current public task is allowed initially')
    obj=json.loads((root/'input/task.json').read_text())
    if set(obj)!={'id','messages'} or not re.fullmatch(r'scibench_\d{6}',obj.get('id','')):
        raise ValueError('Invalid scientific workspace input schema')
    messages=obj.get('messages')
    if not isinstance(messages,list) or len(messages)!=2 or [m.get('role') for m in messages]!=['system','user']:
        raise ValueError('Invalid scientific workspace messages')
    if any(set(m)!={'role','content'} or not isinstance(m.get('content'),str) for m in messages):
        raise ValueError('Invalid scientific workspace message schema')
    return {'status': 'passed', 'files': sorted(files), 'forbidden_names': False}

def command(workspace, venv, shell_command):
    root = Path(workspace).resolve(strict=True)
    venv = Path(venv).resolve(strict=True)
    # All bind sources are fixed trusted paths, never model arguments.
    args = ['bwrap', '--die-with-parent', '--new-session', '--unshare-all', '--cap-drop', 'ALL',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
            '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/home',
            '--dir', '/home/agent', '--dir', '/workspace', '--dir', '/workspace/input',
            '--dir', '/workspace/output', '--dir', '/workspace/tmp',
            '--ro-bind', str(root/'input'), '/workspace/input',
            '--bind', str(root/'output'), '/workspace/output',
            '--bind', str(root/'tmp'), '/workspace/tmp',
            '--ro-bind', str(venv), str(venv), '--clearenv',
            '--setenv', 'PATH', str(venv/'bin') + ':/usr/bin:/bin',
            '--setenv', 'HOME', '/home/agent', '--setenv', 'LANG', 'C.UTF-8',
            '--setenv', 'LC_ALL', 'C.UTF-8', '--setenv', 'TMPDIR', '/workspace/tmp',
            '--setenv', 'OPENBLAS_NUM_THREADS', '1', '--setenv', 'OMP_NUM_THREADS', '1',
            '--chdir', '/workspace', '/bin/bash', '--noprofile', '--norc', '-c', shell_command]
    return args

def limits(cpu_seconds):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (4*1024**3, 4*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32*1024**2, 32*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    # Linux accounts RLIMIT_NPROC against the host UID (including OpenCode
    # threads), not this tool workspace. 256 prevents bwrap namespace creation
    # with nine independent OpenCode sessions. This is uniform for all solvers.
    resource.setrlimit(resource.RLIMIT_NPROC, (4096, 4096))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))

def execute(workspace, venv, script, timeout=180):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Tool timeout must be positive and finite')
    # Capture in RAM only and cap output; no shell receives host env or API keys.
    import selectors
    p = subprocess.Popen(command(workspace, venv, script), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env={'PATH': '/usr/bin:/bin'}, start_new_session=True, preexec_fn=functools.partial(limits, math.ceil(timeout)))
    import time
    deadline = time.monotonic()+timeout
    output = bytearray()
    selector = selectors.DefaultSelector()
    selector.register(p.stdout, selectors.EVENT_READ)
    status = None
    try:
        while selector.get_map():
            if time.monotonic() > deadline:
                status = 'timeout'; break
            for key, _ in selector.select(.2):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj); continue
                output.extend(chunk)
                if len(output) > 65536:
                    status = 'output_limit'; break
            if status: break
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        selector.close()
    return {'exit_code': p.returncode, 'status': status or ('ok' if p.returncode == 0 else 'error'),
            'output': bytes(output[:65536]).decode('utf-8', errors='replace')}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', required=True)
    ap.add_argument('--venv', required=True)
    ap.add_argument('--timeout', type=int, default=180)
    args = ap.parse_args()
    request = json.load(sys.stdin)
    print(json.dumps(execute(args.workspace, args.venv, request['command'], args.timeout), ensure_ascii=False))

if __name__ == '__main__': main()
