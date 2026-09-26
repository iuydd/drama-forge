# 运行边界与恢复

## 项目、授权与配置

本流程只读写 `drama.json` 项目。遇到旧的 `short-drama.json` 五文档项目不自动迁移、不在原目录上运行生产脚本；用户明确要转时另建 `drama.json` 项目，原剧本按 adaptation §5 当多集原稿接入、按 screenplay §1b 规范化，逐项核对映射，原项目保留。

生产前确认本轮范围：哪些集、素材与镜头；模型/档位/尺寸；总提交次数上限（含参考图、起始帧、视频和重拍）；每镜最多 take；成本上限或已接受的计费方式。沿用当前会话或项目中的明确授权，不反复询问。未给足生产条件时先完成写作、分镜等独立工作。

新项目 `profiles` 的六个字段初始为 null，生产前写入本项目已接受的 ref/frame/video 及对应 res。旧项目保留已有明确值；缺项不自动回落到历史模型。底层 `h3_client.py image/video` 必须显式传 `--profile` 和 `--res`，上层 produce 从项目传入。

自动续跑只在已授权任务范围内；不得通过改名、重置 take 或换模型绕过次数/成本边界。现有脚本不执行货币预算核算，主执行者必须用账本统计提交并在每次提交前核对余额；无法可靠估算成本或对账时暂停生产，不声称脚本已强制封顶。范围、价格或模型变化需要补充授权。供应商明确终态失败才允许按已授权重试次数重投。

## 提交结果未知

提交前将 request_id、内容指纹、任务名、输出路径写入并刷盘为 `submission_intent`。拿到供应商 ID 后写 `submitted`。超时、响应解析失败，或 intent 后进程崩溃均可能已经计费；未解决的 intent 会阻止本项目后续提交。

以下命令中的 `{scripts}` 替换为技能 scripts 绝对路径，`{project}` 替换为项目路径：

```text
python3 {scripts}/h3_client.py --root {project} unresolved
python3 {scripts}/h3_client.py --root {project} reconcile --request-id REQUEST_ID --job PROVIDER_JOB_ID --evidence "供应商历史中核实的对应关系"
python3 {scripts}/h3_client.py --root {project} collect --job PROVIDER_JOB_ID --kind video --out OUTPUT_PATH
```

`reconcile` 只记人工/供应商对账结果，不会自动查询或证明任务对应关系。先核对账户、提交时间、类型、内容与输出目标；证据不含 token。已找到任务 ID 就收回该任务；只有供应商记录/支持明确证实未受理，才可解除未决状态：

```text
python3 {scripts}/h3_client.py --root {project} reconcile --request-id REQUEST_ID --not-submitted --evidence "供应商确认未受理的证据"
```

不能因为一时查不到就断言未提交。不要删除账本或伪造证据解除阻断。旧版 `post_failed` 没有 request_id，升级前留下的这类记录应先与供应商历史核对；新恢复命令不自动迁移或猜测旧记录。

已成功提交但下载失败记为 `download_failed`，继续 collect，不能当作生成失败而重拍。损坏的账本会阻止提交，先从备份/供应商记录恢复。

## 停止与交付

等待空闲与提交前都检查 STOP/DEADLINE。已经发出的任务允许收回，停止条件不取消已计费任务。删除 STOP 或延后 DEADLINE 不等于扩大原有授权范围。

Git 是可选交付策略：检查当前分支、未提交修改和远端；仅按明确授权同步，不自动推主分支。代理模型与看图工具遵循宿主环境能力，不要求 Claude 专用目录或固定模型。
