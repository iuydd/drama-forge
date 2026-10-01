---
name: ai-drama-production
description: 创作和制作 AI 短剧，包括剧本改写、人物道具场景资产、分镜、视频提示词、声音剪辑与实片审核。由同一个 agent 先完成前期，再按授权生产；MiniMax H3 默认直接使用资产参考图。
metadata:
  version: "4.7.6"
  package_version: "4.7.6"
  content_version: "4.7.6"
  workflow_version: "4.3.0"
  workflow_mode: "upfront_self"
  language: "zh-CN"
  package_role: "integrated"
  media_policy_version: "4.2.0"
---

# AI 短剧制作

先确认本次是写稿、改稿、提示词、审核还是实际制作，恢复相关成果，只完成授权范围。同一个 agent 负责前期与生产；纯文本任务不等待媒体服务，也不自动触发生成。

人从 [README](README.md) 找入口。AI 先读 [00 工作契约](references/00-contract.md)，再按下表读当前任务需要的章节；同版内容仍在上下文中时可复用。现行规则以 `references/00–11` 为源，`assets/source.md` 是同步全文，历史载荷不覆盖当前规则。

## 三个默认选择

- **按用户口味写故事。**先写人物目标、冲突与应对，不为创新求怪；常见、强大的能力可以成立，不靠不断加限制收回收益。
- **场景共源，独立资产直接送 H3。**同一房间先锁共同布局和场景母资产，各机位从同一根派生并跨图验收；视频绑定目标机位的真实场景图。人物、道具、场景作为有序 reference 输入，不融合首帧，不上传前镜尾帧；安静背景不硬加运动。
- **剧本能懂、视频不懂时先查媒体表达。**保留已成立的剧情，定位分镜、素材或剪辑在哪里丢失信息；正文盲读不能代替实片盲看。

## 按任务阅读

| 当前任务 | 接着读 | 交付内容 |
|---|---|---|
| 原创、修稿、正文审读 | [01 故事](references/01-story.md)、[02 因果](references/02-opening-causality.md)、[03 表演](references/03-performance.md)、[09 审核](references/09-review-repair.md)；改编另加 [04](references/04-adaptation.md) | 可直接阅读的正文与修改依据 |
| 分镜、资产、图片/视频 prompt | [05 素材与状态](references/05-space-assets.md)、[06 分镜与请求](references/06-storyboard-prompts.md)；人物表演补 03，声音补 [07](references/07-animatic-audio.md) | 有叙事动机的机位与运动、可观察表演、完整 prompt、有序资产、起终状态与验收点 |
| 整集前期包 | [前期清单](references/brain-reading-guide.md) | 指定范围的剧本、资产、任务、声音剪辑和有限返修方案 |
| 实际生成与生产 | [生产清单](references/agent-reading-guide.md)、[10 执行](references/10-execution.md)、[11 交接](references/11-handoff.md) | 真实产物、任务账与实际检查 |
| 剪辑、实片审核、视频看不懂 | 06、07、[08 剪辑](references/08-editing.md)、09；按问题补 03、05 | 当前采用版本的证据、信息断点与对应修复 |
| 隔离盲看 | 仅 [独立盲看指令](references/blind-review.md)、实际媒体及允许前情 | 观众实际看到、听到和理解的内容 |

## 执行顺序与完成边界

**已锁事实 → 声画安排 → 最终请求 → 实片与采用证据 → 修复或交付。**

每镜从共同现场推导可见范围与完整起终状态，写法和最终请求检查以 05/06 为准；说完台词不等于现场归零。实际审核按 09 核对同一采用版的完整事件、全场对象、声音与观众理解；保留原设计成立的裁切、遮挡、省略和悬念，局部正确不抵消其他硬伤。

完整前期先写自然正文，再按 [记录格式](prompts/record-format.txt) 与 [schema](schemas/brain-response.schema.json) 序列化，用 `preproduction.py assemble / validate` 检查到 `PLAN_COMPLETE`；它只表示结构完整。生产绑定真实已验收资产，冻结请求后执行原有 G0–G4。方案有错就修订并使相关检查失效，不能在绑定时悄悄改词改镜。

复发问题按 09 定位并有限返修；批次停止、任务收尾、独占接管与费用按 10。原有有效授权在范围内继续使用。

只在用到工具时读 [模板索引](references/template-index.md) 与 [工具说明](references/tooling.md)。机器角色路线见 [role-reading-map.json](config/role-reading-map.json)，旧阶段凭据见 [阅读路线](references/reading-routes.md)。`brain` 等历史字段保留兼容，不要求第二个会话；用户明确选择外部 Brain 才启用 [兼容工作流](references/upfront-workflow.md)。
