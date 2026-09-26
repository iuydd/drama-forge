# 运行边界与恢复

## 项目、授权与配置

本流程只读写 `drama.json` 项目。遇到旧的 `short-drama.json` 五文档项目不自动迁移、不在原目录上运行生产脚本；用户明确要转时另建 `drama.json` 项目，原剧本按 adaptation §5 当多集原稿接入、按 screenplay §1b 规范化，逐项核对映射，原项目保留。

生产前确认本轮范围：哪些集、素材与镜头；模型/档位/尺寸；总提交次数上限（含参考图、起始帧、视频和重拍）；每镜最多 take；成本上限或已接受的计费方式。可以沿用、不反复询问的授权只有两种：当前会话里用户的原话，或决策记录里 `拍板人: 用户` 且抄了原话和日期的行。`drama.json` 里已有的值、`拍板人: 代理` 的行、模板默认值（含契约 §8 的集数和 take 数）、历史项目都不算授权（SKILL.md「防钻空子总则」第 2 条）。未给足生产条件时先完成写作、分镜等独立工作。

新项目 `profiles` 的六个字段初始为 null，生产前写入用户在对话里说定的 ref/frame/video 及对应 res，并在决策记录记一行 `拍板人: 用户`、原话点名了这个模型、档位或分辨率；指不到这样一行的值当作没定。镜头和参考图条目里不写档位与分辨率（脚本仍会优先读它们，写了就是绕过 `profiles`）。旧项目保留已有明确值；缺项不自动回落到历史模型。底层 `h3_client.py image/video` 必须显式传 `--profile` 和 `--res`，上层 produce 从项目传入。

自动续跑只在已授权任务范围内；不得通过改名、重置 take 或换模型绕过次数/成本边界：提交次数和每镜 take 数按 `脚本/jobs.jsonl` 数（含 intent，覆盖所有通道），挪走或改名文件不重置计数；`--jobs N` 并行要用户原话单独授权并发。现有脚本不执行货币预算核算，主执行者必须用账本统计提交并在每次提交前核对余额；无法可靠估算成本或对账时暂停生产，不声称脚本已强制封顶。范围、价格或模型变化需要补充授权。供应商明确终态失败才允许按已授权重试次数重投。

## 提交结果未知

提交前将 request_id、内容指纹、任务名、输出路径写入并刷盘为 `submission_intent`。拿到供应商 ID 后写 `submitted`。超时、响应解析失败，或 intent 后进程崩溃均可能已经计费；未解决的 intent 会阻止本项目后续提交。

以下命令中的 `{scripts}` 替换为技能 scripts 绝对路径，`{project}` 替换为项目路径：

```text
python3 {scripts}/h3_client.py --root {project} unresolved
python3 {scripts}/h3_client.py --root {project} reconcile --request-id REQUEST_ID --job PROVIDER_JOB_ID --evidence "供应商历史中核实的对应关系"
python3 {scripts}/h3_client.py --root {project} collect --job PROVIDER_JOB_ID --kind video --out OUTPUT_PATH
```

`reconcile` 只记人工/供应商对账结果，不会自动查询或证明任务对应关系。先核对账户、提交时间、类型、内容与输出目标；证据不含 token。已找到任务 ID 就收回该任务；只有供应商记录/支持明确证实未受理，才可解除未决状态。`--not-submitted` 的 `--evidence` 只收两种：存进项目 `脚本/` 的供应商任务列表导出或客服回复（覆盖 intent 前后各 30 分钟，写文件路径）；或决策记录里 `拍板人: 用户` 的行编号。"查不到""列表里没有"这类一句话不算证据：

```text
python3 {scripts}/h3_client.py --root {project} reconcile --request-id REQUEST_ID --not-submitted --evidence "供应商确认未受理的证据"
```

不能因为一时查不到就断言未提交。不要删除账本或伪造证据解除阻断。旧版 `post_failed` 没有 request_id，升级前留下的这类记录应先与供应商历史核对；新恢复命令不自动迁移或猜测旧记录。

已成功提交但下载失败记为 `download_failed`，继续 collect，不能当作生成失败而重拍。损坏的账本会阻止提交，先从备份/供应商记录恢复。

## 停止与交付

等待空闲与提交前都检查 STOP/DEADLINE。已经发出的任务允许收回，停止条件不取消已计费任务。STOP 和 DEADLINE 只由用户删改，代理不删也不改；用户删了 STOP 或延后 DEADLINE，也不等于扩大原有授权范围。

Git 是可选交付策略：检查当前分支、未提交修改和远端；仅按明确授权同步，不自动推主分支。看图工具遵循宿主环境能力，不要求 Claude 专用目录；子代理一律用 `scripts/isolated_agent.sh` 起，模型不低于主会话（脚本拒绝降级），拿不到生成密钥、不提交生成任务。任务书优先用 `scripts/task_pack.py build` 构建成任务包再交给 isolated_agent.sh（启动前 verify：材料、模板或工具在构包后改过就拒绝启动）；reviewer 用纯文本任务书会收到警告。
