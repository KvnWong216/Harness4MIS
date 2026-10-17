#!/bin/zsh
cd "${0:A:h}"
task_python="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [[ -n "$MIS303_PYTHON" ]]; then
  task_python="$MIS303_PYTHON"
fi
if [[ ! -x "$task_python" ]]; then
  print '找不到 Codex 文件处理环境，请先在 Codex 中启用文档与演示文稿插件。'
  read 'task_answer?按回车关闭'
  exit 1
fi
"$task_python" run.py
