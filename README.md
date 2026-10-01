# AI 短剧制作

当前版本 **4.7.6**。这个 Skill 按你的题材写故事，并把剧本做成素材、视频和成片。同一个 agent 可以完成前期与生产，只写剧本时就在正文阶段结束。

默认流程是：**剧本与分镜 → 独立人物/道具/场景资产 → 有序参考图直接送 MiniMax H3 → 视频检查 → 声音剪辑 → 实片终验。**不先融合首帧。

## 安装与更新

GitHub 仓库名保留为 `drama-forge`，当前 Skill 名称是 `ai-drama-production`。首次安装到支持 `~/.agents/skills` 的 agent：

```bash
git clone https://github.com/iuydd/drama-forge.git ~/.agents/skills/ai-drama-production
```

已经通过 Git 安装时，在该目录运行 `git pull --ff-only`；已有目录不是 Git checkout 时，先备份，再替换安装包。模型通道和授权按 [工具说明](references/tooling.md) 配置。

本仓库已用当前 Skill 替换旧版 DramaForge。旧版的项目文件和命令不会自动迁移；继续旧项目或切换生产方式前，先读 [升级说明](UPGRADE.md)。

## 从哪里开始

| 你要做什么 | 打开这里 |
|---|---|
| 让 AI 工作 | [SKILL.md](SKILL.md)：范围、默认选择和任务路由 |
| 写故事或修稿 | [01 故事](references/01-story.md)、[02 因果](references/02-opening-causality.md)、[03 表演](references/03-performance.md) |
| 做素材、分镜和 prompt | [05 素材与状态](references/05-space-assets.md)、[06 分镜与请求](references/06-storyboard-prompts.md) |
| 剧本能懂，视频表达不清 | [09 信息断点与返修](references/09-review-repair.md)，按问题查 05–08 |
| 开始完整制作 | [前期清单](references/brain-reading-guide.md)、[生产清单](references/agent-reading-guide.md) |
| 找命令、模板或升级变化 | [工具说明](references/tooling.md)、[模板索引](references/template-index.md)、[UPGRADE](UPGRADE.md) |

不用读完文件夹。可以直接说：“用这个 Skill 写一集职场短剧，主角优势要真正有用，不要为了创新硬编设定。”也可以指定只改分镜、声音或剪辑。

## 文件各管什么

- `references/00–11`：现行方法，按工作读取；同一规则只在负责的章节维护。
- `templates/`、`schemas/`、`prompts/`：项目模板与机器格式，需要制作包时使用。
- `tools/`、`scripts/`、`config/`、`agents/`：工具、同步、路由与界面配置。
- `assets/`：同步全文与仍被工具使用的兼容载荷。旧报告、过时文档副本和缓存不随现行安装包保留。

保持同一现场和真实版本，比不断加禁令更重要。剧本可读不等于视频可懂，模型生成成功也不等于采用通过。修改方法后同步派生文件；具体维护命令见工具说明。

公开仓库沿用原有 MIT License；方法来源与研究链接见 [来源说明](references/sources.md) 和 [THEORY_PROVENANCE.json](THEORY_PROVENANCE.json)。外部链接内容的权利归原作者。
