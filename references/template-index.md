# 模板索引

所有路径相对于 Skill 根目录。模板是待填结构，不是已经通过的项目；只读取当前工作需要的文件。

| 当前工作 | 从哪里开始 |
|---|---|
| 写剧本、人物和开头 | `tools/short-drama-writer/assets/templates/`；先写正文，再填 brief、bible、episode |
| 整集前期包 | `templates/project-request.json`、`schemas/brain-response.schema.json`、`prompts/record-format.txt` |
| 已接受资产与绑定任务 | `templates/accepted-assets.json`、`templates/execution-packet.json` |
| H3 参考图视频任务 | `templates/h3-reference-video-task.json`；含有序资产、背景变化与参数槽位 |
| 资产设计和文件清单 | `tools/reference-builder/templates/` |
| 单镜提示词、空间与连续性 | `tools/visual-continuity-prompter/templates/` |
| 运行配置、审核、剪辑与交付 | `tools/production-ops/templates/` |

reference 视频的任务字段与顺序见 [06 分镜与提示词](06-storyboard-prompts.md)。不要套用旧 examples 中的 primary/start_frame 作为新视频默认输入；每镜真实请求需要与本次选用模式一致。

`tools/production-ops/templates/` 中常用文件：

| 需求 | 模板 |
|---|---|
| 首次部署与能力实测 | `deployment.json`、`live-eval-plan.json` |
| 完整 prompt 与编译后端 | `prompt-ir.json`、`prompt-backend.json` |
| 空间、状态、切镜连续性 | `continuity-plan.json`、`continuity-bindings.json` |
| 任务门禁与回传 | `production-gate-spec.json`、`brain-return.json` |
| 后期与交付 | 按本项目实际需要读取 timeline、presentation、audio、delivery 对应文件 |

`assets/brain-skill.md`、`prompts/agent-to-brain*.txt` 仅供显式选择旧外部 Brain 的项目；默认不使用这条路线。示例与测试 fixture 不直接投产。
