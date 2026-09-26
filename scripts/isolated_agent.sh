#!/bin/sh
# 隔离子代理：只给 drama-forge SKILL.md + 任务，不带 CLAUDE.md、其他 skill、插件 hook、MCP。
# 用法：isolated_agent.sh <工作目录> <任务文本或任务文件>   （输出=子代理最终回复）
set -e
SKILL_DIR=$(cd "$(dirname "$0")/.." && pwd)
WORKDIR=${1:?工作目录}; TASK=${2:?任务}
[ -f "$TASK" ] && TASK=$(cat "$TASK")
SYS="$(cat "$SKILL_DIR/SKILL.md")

---
你是 drama-forge 的子代理。上面是你唯一的规则。skill 目录在 $SKILL_DIR，references/、scripts/、assets/ 按需自己读。只做任务里写的事，做完用中文简短汇报产物路径和结论。"
cd "$WORKDIR"
exec claude -p --model "${DF_AGENT_MODEL:-opus}" \
  --setting-sources "" --strict-mcp-config --disable-slash-commands \
  --dangerously-skip-permissions --add-dir "$SKILL_DIR" \
  --system-prompt "$SYS" "$TASK"
