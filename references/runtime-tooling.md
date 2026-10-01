> 4.5.0 入口：先读 `SKILL.md`，按本次任务使用前期或生产清单。当前 agent 自己创作和执行，`config/role-reading-map.json` 使用 integrated 路线。`assets/brain-skill.md` 是显式 legacy 的外部 Brain 兼容载荷，不是当前创作规则。

# 离线工具入口与能力边界｜4.2

在Skill根目录执行以下命令；文件路径由当前项目实际提供，示例不是已有用户文件。依赖清单为`requirements-offline.txt`，不自动安装服务或字体。视频/音频处理另需实际ffmpeg/ffprobe。

```bash
python scripts/runtime.py doctor
python scripts/runtime.py doctor --project /absolute/project
python scripts/run_tests.py --report /absolute/test-report.json
python scripts/runtime.py compile-prompt --ir /project/ir.json --backend /project/backend.json
python scripts/runtime.py validate-return --file /project/return.json --root /project
python scripts/runtime.py pack-return --file /project/return.json --root /project --out /exchange/return.zip
python scripts/runtime.py unpack-return --capsule /exchange/return.zip --root /new/project
python scripts/runtime.py diff-scopes --before /project/plan-old.json --after /project/plan-new.json
python scripts/runtime.py metrics --file /project/actual-runs.json --root /project
python scripts/runtime.py probe-media --file /project/shot.mp4 --kind video
```

上述命令不提交生成。目标目录应存在；打包/导入不覆盖不同内容。validate-return结果为待审而非接受。doctor只核依赖/版本/记录，不会将NOT_RUN变成已部署。

## 当前模块职责

H3 reference 视频从 [`templates/h3-reference-video-task.json`](../templates/h3-reference-video-task.json) 开始。任务使用 `mode: "video_reference"`、`video_input: "references"`、`image_mode: "reference"`；`required_asset_ids` 冻结本镜全部所需资产，`inputs` 使用 `role: "asset_ref"` 和连续 `upload_index`。`background_motion` 的完整描述也要出现在最终 prompt 中。

```bash
python3 tools/production-ops/scripts/preproduction.py export-h3 --plan /project/preproduction-plan.json --registry /project/accepted-assets.json --root /project --task TASK_ID --out /project/h3-request.json
```

此命令绑定已接受的真实文件并离线导出有序图片请求，不联网、不提交生成，`ready_for_submission` 保持 false。生产宿主仍核验实际 H3 参数、费用授权及媒体门禁，再向 `/api/v1/generate` 提交。多人/物体覆盖使用 `shot.entity_asset_ids` 映射和真实 `asset_registry`，reference 预检不要求融合首帧审核。

### 把已锁可见状态写入最终提示词

使用 `shot.ensemble` 时，先从同一 bundle 派生当前机位的描述：

```bash
python3 tools/visual-continuity-prompter/scripts/scene_continuity.py --bundle /project/ensemble.json --clauses
```

图片任务另加 `--image`，只取首个时间窗口。返回的 `context_clauses` 包含可见主体、背景、行为、局部/反射范围和时间段；画外或完全遮挡的实体不强迫出现在 prompt。普通与 nine 编译自动使用这段文本。手写锁定提示词须在冻结前保留它；IR 路径把它作为 `kind: "context"`、`required: true` 的条款，条款 ID 加入 `priority.hard` 后再编译，不将它标为可由参考图省略。可按时间窗口拆成多个条款，保持每个完整块及原顺序。

最终检查在准确对白范围之外核对这些冻结块，避免只在台词里念出画面描述也被算成覆盖。块内不能在冻结后缩写、漏掉配角/物件或局部范围；合法别名和表述先改 `view_plan` 来源再派生。失败时指出缺失或失序的可见块并停止，不悄悄往已锁文本后面补字。`compile-prompt` 单独只做 IR 编译，没有 shot 的 ensemble；生产仍须经过完整 shot 的最终检查，不能把单独编译成功当作提交许可。

该检查验证声明传递，不解析自然语言的全部含义，也不读取视频数人数。额外语句是否与冻结块矛盾、可见范围是否符合机位，以及模型是否生成正确，仍按 06/09 做当前版本的请求与媒体审查。

### IR 对白转换不得丢掉指导

`speech_format: "colon"` 会改写说话人包装，因此 `speech.text` 只接受四种可证明无损的完整内容：`text_spoken`、`只说：` + 原文、`speaker` + `说：` + 原文、`speaker` + ` says: ` + 原文；可附一份换行后的完整 `Delivery, not spoken: ` + 当前 `delivery`。其他内容明确拒绝，避免把藏在正文里的声线、连读或表演说明丢掉。

遇到拒绝，回 IR 来源把额外声音指导放进已有 `delivery`，动作/镜头事实放进对应独立条款，保留准确台词后重编译、重新冻结；不靠截掉说明或自动换格式通过。`literal` 保留原正文，两种格式都保留独立 `delivery`。这是文本传递检查，不证明声线、节奏或真实表演合格。

| 模块（production-ops/scripts） | 实际能力 | 不能证明/尚需提供 |
|---|---|---|
| prompt_contract | 脑写IR、硬约束/资源冲突、后端文本编译、准确台词保留 | 任意自然语言无矛盾、模型服从、后端实测 |
| fidelity_contract / sequence_continuity | 自动事实比较、时序/覆盖/同机位投影、实际切点和回访记录 | 从媒体自动识别所有物体/情绪 |
| spatial_math / world_constraints | 明确参照几何、容差、区间转换、声明式关系冲突 | 图像恢复3D、遮挡推断、物理仿真 |
| trusted_runtime / host_validator | 保护域签名网关参考、一次提交/回执、video/pre_video组合校验 | 用户宿主已隔离、其他模式适配器已安装 |
| brain_exchange | 精确回传验证、去重安全胶囊、事务待审与签名接受 | 自动联系ChatGPT、自动语义合并创作 |
| workflow_support | 有关范围摘要/证据复用、关键链排序、限定技术替代 | 自动减少全部费用、配置相同即质量相同 |
| media_validation | 实际图片解码、ffprobe、盲看文件白名单 | 视觉/听音正确、审阅者记忆真正隔离 |
| text_composite | 本地字形覆盖检查、受控字稿、平面贴图/遮挡、随笔路径显露 | 实际字体权利、自动追踪、弯纸或真实书写成功 |
| evaluation_tools | 分开合成/真实指标、漏检/误杀/UNKNOWN和实际成本计数 | 无真实样本的成功率或非劣性结论 |

既有编剧工具、参考构建、visual compiler、ensemble、剪辑时钟、bridges、presentation、费用账本、校准与修复工具继续保留。运行4.2生成需完整当前policy/IR/真实输入；legacy工具仍可用于旧项目维护，但不能宣称通过4.2门禁。

[格式](handoff-format.md) · [序列](sequence-format.md) · [宿主接入](deployment.md) · [依据](sources.md)

## 前期包与可选外部交接（底层工具政策仍 4.2）

当前 agent 按现行章节写前期记录，再用 `preproduction.py assemble/validate/bind` 组装、拒绝漏集与循环依赖、绑定真实已接受输入，不调用媒体模型。`prepare` 与 `brain_transport.py` 属于显式选择的旧外部 Brain 兼容路线，不能自动发送过时规则。`brain_transport.py` 还需要明确模型、调用额度、输出上限与授权才联网；tools=[]，不生成图片或视频。完整兼容命令见[外部工作流](upfront-workflow.md)。

新execution-packet-1由production_supervisor依据前期plan创建，load_task核等价绑定后继续原4.2语义/输入/质量门禁；不是删除brain_required、关闭fidelity或伪造chatgpt_brain批准。运行时接受不使用旧WorkflowStore向大脑求批准，记录实际生产审核即可；保护域仍需要部署。
