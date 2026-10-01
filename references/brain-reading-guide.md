# 前期阅读清单

默认由当前 agent 自己完成前期。文件名中的 `brain` 保留给旧接口使用，不表示必须找另一个 AI。

先写用户能读的正文，再提取制作字段。纯剧本任务只读第一行；完整制作按需要依次读完相关阶段，改编才需要 04。机器路线 `upfront` 提供完整前期阅读包，单项工作选 `story_original`、`board` 等对应阶段。

| 工作 | 阅读章节 | 完成标志 |
|---|---|---|
| 剧本、修稿与正文审读 | [00](00-contract.md)、[01](01-story.md)、[02](02-opening-causality.md)、[03](03-performance.md)、[09](09-review-repair.md) | 符合用户题材和口味，有人物冲突、行动和进展的自然正文，不为创新求怪 |
| 原著改编 | 上一行，加 [04](04-adaptation.md) | 保留已锁事件与人物承诺 |
| 分镜、资产、视频 prompt | [03](03-performance.md)、[05](05-space-assets.md)、[06](06-storyboard-prompts.md) | 独立资产、有序参考图、空间关系和时序运动写全 |
| 声音与剪辑设计 | [02](02-opening-causality.md)、[03](03-performance.md)、[07](07-animatic-audio.md)、[08](08-editing.md) | 准确对白、声音时机、剪辑和必须保留的事件 |
| 验收与有限返修 | [09](09-review-repair.md)；了解 [隔离盲看要求](blind-review.md) | 具体观察标准与完整可执行分支，不代填 PASS |
| 序列化与校验 | [前期包格式](brain-handoff.md)、[记录字段](../prompts/record-format.txt)、[schema](../schemas/brain-response.schema.json) | 本次范围齐全，assemble / validate 通过 |

默认不设计融合首帧。资产通过之后就作为 H3 reference 输入；prompt 说明谁、什么、在哪、怎样行动及背景怎样变化。前期无需等待真实资产，但应写好稳定资产 ID 和槽位，不能伪造文件、hash 或验收结果。

生产暴露出方案错误时，回到这里改 revision，列出失效范围再校验。用户明确要求外部 Brain 才启用[外部前期工作流](upfront-workflow.md)，当前会话仍保留生产职责和真实验收边界。
