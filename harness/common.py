from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('MIS303_DATA_DIR', ROOT / 'runs')).resolve()
DEPENDENCIES = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'


def now():
    return datetime.now(timezone.utc).isoformat()


def local_date(instant):
    return datetime.fromisoformat(instant).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def runtime(name):
    env = os.environ.get('MIS303_' + name.upper())
    if env:
        return env
    choices = {
        'node': [DEPENDENCIES / 'node/bin/node'],
        'python': [DEPENDENCIES / 'python/bin/python3'],
        'codex': [Path('/opt/homebrew/bin/codex')],
        'soffice': [DEPENDENCIES / 'bin/override/soffice'],
    }
    for p in choices.get(name, []):
        if p.exists():
            return str(p)
    found = shutil.which('python3' if name == 'python' else name)
    if not found:
        raise RuntimeError(f'找不到 {name}，请在启动设置中指定其位置。')
    return found


def skill_dir(kind):
    configured = os.environ.get('MIS303_' + kind.upper() + '_SKILL')
    if configured:
        return Path(configured)
    base = Path.home() / '.codex/plugins/cache/openai-primary-runtime' / kind
    matches = sorted(base.glob(f'*/skills/{kind}'))
    if not matches:
        raise RuntimeError(f'缺少 {kind} 文件生成组件，请先在 Codex 中启用相应插件。')
    return matches[-1]


def safe_name(name):
    name = Path(str(name).replace('\\', '/')).name
    return ''.join(c for c in name if c.isalnum() or c in ' ._-()（）')[:150] or 'file'


def under(root, relative):
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if result != root and root not in result.parents:
        raise ValueError('文件路径无效')
    return result
