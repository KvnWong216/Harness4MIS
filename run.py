#!/usr/bin/env python3
import argparse
import importlib.util
import subprocess
from harness.common import runtime, skill_dir


def doctor():
    for name in ['docx', 'pypdf', 'pypdfium2', 'PIL', 'openpyxl']:
        print(name + ': ' + ('可用' if importlib.util.find_spec(name) else '缺少'))
    for name in ['node', 'codex', 'soffice']:
        try:
            print(name + ': ' + runtime(name))
        except RuntimeError as exc:
            print(str(exc))
    for name in ['documents', 'presentations']:
        try:
            print(name + ': ' + str(skill_dir(name)))
        except RuntimeError as exc:
            print(str(exc))
    subprocess.run([runtime('codex'), 'login', 'status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MIS303 作业助手')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--doctor', action='store_true')
    args = parser.parse_args()
    if args.doctor:
        doctor()
    else:
        from harness.server import serve
        serve(args.port)
