# 生产阅读清单

默认由完成前期的同一个 agent 继续生产。先确认前期包通过结构校验，当前素材、任务与授权属于同一项目和版本。结构通过不是实片通过。

| 工作 | 阅读章节 | 实际要做的事 |
|---|---|---|
| 启动、恢复和调度 | [00](00-contract.md)、[10](10-execution.md)、[11](11-handoff.md) | 识别本次范围、可用通道、已有任务与费用边界 |
| 人物、道具、场景资产 | [05](05-space-assets.md)的“角色资产生成”及场景/道具部分、[09](09-review-repair.md) | 角色先按戏份与景别分级、复用已有素材，写清每张生图的职责与状态；分别生成、验收并登记真实资产 |
| 绑定输入与生成视频 | [03](03-performance.md)、[05](05-space-assets.md)、[06](06-storyboard-prompts.md)、[07](07-animatic-audio.md) | 按既定顺序上传 reference 图；把机位与运镜起止、人物动作和语气写入完整 prompt，继承道具与现场状态 |
| 预演与声音 | [02](02-opening-causality.md)、[03](03-performance.md)、[07](07-animatic-audio.md)、[09](09-review-repair.md) | 实际制作、听音与核对句界，不改已锁台词 |
| 剪辑 | [06](06-storyboard-prompts.md)、[07](07-animatic-audio.md)、[08](08-editing.md)、[09](09-review-repair.md) | 选择实际源范围，保住事件、声音和连续性 |
| 审核与返修 | [09](09-review-repair.md)，按问题补 03、05–08 | 看当前媒体，按预写分支修；方案错误回前期修订 |
| 交付 | [08](08-editing.md)、[09](09-review-repair.md)、[10](10-execution.md)、[11](11-handoff.md) | 真实终片、当前版本报告、费用和续作记录 |

默认 reference 工作流跳过 `start_frames`：不生成融合首帧，不接上一镜尾帧。旧首帧能力仅供明确采用旧模式的项目维护，不是新任务的先决条件。

要修改剧情或新增 prompt，回到[前期清单](brain-reading-guide.md)由当前 agent 完成，不强制转交另一个会话。不要在素材绑定期间静默改写冻结方案。

盲看例外：独立审核者只获得 [blind-review.md](blind-review.md)、实际媒体和允许前情，不获得本清单、剧本答案或整个项目目录。

工具路线由 `config/role-reading-map.json` 提供；[命令与能力边界](runtime-tooling.md)只在运行对应工具时读取。
