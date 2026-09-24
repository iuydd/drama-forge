---
name: drama-forge
description: 爆剧引擎 / DramaForge：从点子无人值守地制作商业爽剧短剧，覆盖剧情、剧本、视觉资产、分镜、MiniMax H3 生成、ASR 审片、自动重拍与剪辑。用户要求全自动做短剧、从点子出成片、继续短剧流水线或接着做 EP00x 时使用。Use for autonomous AI short-drama production from premise to final cut.
license: MIT
---

# 爆剧引擎 / DramaForge

把一个点子做成能追看的商业爽剧成片，中途不问人。剧情比画质重要；台词要多、反应要快；一镜一人。

这套 skill 是目前网上公开的短剧 skill 的精华合集：六套来源（short-drama 十一件套、shuohao-skills、su-ai-short-drama、cinematic-video-prompt-engineer、director、AI-drama-pound）逐个通读、逐条提炼，只留下对全自动商业爽剧真正有用的方法，再把它们写成一条能跑的流水线和 27 道机械门。各家取了什么见 README 的来源表。

## Quick Start

```bash
S=~/.agents/skills/drama-forge/scripts
python3 $S/selftest.py                                                   # 安装后跑一次，离线
python3 $S/project_tool.py init <项目目录> --title "剧名" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 $S/project_tool.py next <项目目录>                               # 任何时候：下一步该做什么
```

生产需要环境变量 `H3_API`（你的 H3 中转地址，也可写在 `drama.json` 的 `api_base`）和 `H3_STUDIO_TOKEN`（只从环境读，不落盘）；审片需要 `ASR_PY`（装了 faster-whisper 的 python，例如 `~/.venvs/asr/bin/python`；不设则自动扫 `~/.venvs/*`）。

## 硬约束（一直有效）

1. **全自动**：不用 AskUserQuestion，不停下问人。每个替人拍的板写进 `项目开发/决策记录.md`。唯一停下的情况：生成接口连不上或没有 token（写作阶段照做，生产阶段停并写明原因）。
2. **串行**：一次只提交一个生成任务；提交前查 `/api/status` 空闲。POST 永不自动重发；先查账本收回未收回的任务。
3. **一镜一人**：一个镜头只拍一个人或一双手；每镜约 5 秒、成片留 4–5 秒；对白长的按容量加长（≤8 秒），不加速。
4. **生成画面不出字**：字幕、面板、印章字全部后期叠加；手机屏幕背对镜头。
5. **台词逐字等于剧本**（G09/G10）；能力规则/装置条款先改系列简报再进剧本。
6. **剧情优先**：审片只看剧情、动作可读、台词完整、有无出字、有没有认错人；画质不作重拍理由。
7. **写作与审查分离**：写的子代理不审自己写的；reviewer 子代理只出结论和修订要求。派子代理一律用与主会话同级的模型（显式 `model: opus`）。
8. 不删产物：重拍开新 take；参考图重出改名归档。

## 项目与契约

目录布局、ID、`shots.json` / `refs.json` / `review.json` 字段、27 道机械门、自动决策默认表、续跑与收回：[pipeline-contract.md](references/pipeline-contract.md)。开工先读它，全程按它对账。

## 阶段与门

写作阶段（A–E）可多集并行；生产阶段（F–J）全项目串行。每阶段：读对应参考 → 产出 → 跑门 → 修到 0 error → reviewer 子代理（C、E 两阶段）→ 下一阶段。

| 阶段 | 做什么 | 读 | 产出 | 门 / 命令 |
|---|---|---|---|---|
| A 立项 | 四问定爽点、选一个主类型、人物与反派手段、装置条款、分集走向 | [story-engine.md](references/story-engine.md) §1–4、§10 | `项目开发/系列简报.md`、`drama.json` | 模板方括号清零；`project_tool.py next` 不再指 A |
| B 情绪集纲 | 每集一行：受什么气、底牌与谁先知道、主角行动、反派失去、兑现、新问题、交接事实 | story-engine §5–6、§8 | `项目开发/情绪集纲.md` | 每格具体；反派失去非空 |
| C 剧本 | 集纲那一行扩成可拍剧本；台词多、反应快、按用途写 | [screenplay.md](references/screenplay.md) | `EPxxx/剧本.md` | `shots_tool.py check`（G16 剧本部分先跑：新建空 shots.json 也能报剧本门）；reviewer 子代理按 story-engine §11 + screenplay §10 审，两轮内清 Major |
| D 视觉设定 | 人物/地点/道具条目、锚点、音色、锁；refs.json 增量 | [visual-assets.md](references/visual-assets.md) | `EPxxx/视觉设定.md`、`参考图/refs.json` | `shots_tool.py check-refs`（G18–G20） |
| E 分镜与提示词 | 每镜：职责、主体朝向、冻结关键帧、起始帧提示词、动作、视频正文、台词时点、叠加、边界链 | [storyboard-keyframes.md](references/storyboard-keyframes.md)、[video-prompts-h3.md](references/video-prompts-h3.md) | `EPxxx/shots.json` → `shots_tool.py render` 出三份 md | `shots_tool.py check` 0 error；warn 逐条判断，豁免写 `waive`；reviewer 子代理看渲染出的分镜.md |
| F 参考图 | 身份图、底板、道具图 | visual-assets §7–8、[production-and-review.md](references/production-and-review.md) §4 | `参考图/IMG-*.png` | `produce.py refs`；模型 Read 每张 PNG 目检，不过 `--retake` |
| G 起始帧 | 每镜起始帧 | production-and-review §3–4 | `起始帧/F_*_t*.png` | 先金丝雀一镜；`produce.py frames`；逐张目检（一人、朝向、持物、留空、无字、像参考）；`review_tool.py mark --frame-take` |
| H 视频 | 每镜视频，ASR 不达标自动重拍 | production-and-review §5、§7 | `视频/V_*_t*.mp4` | `produce.py videos --asr` |
| I 审片 | 接触表 + ASR + 模型看图；定 take、取用区间、结论 | production-and-review §5–8 | `审查/<EP>-review.json`、`<EP>-审片.md` | `review_tool.py sheets / asr / auto / report`；模型看接触表后 `mark`；retake 回 H |
| J 剪辑 | 取用、字幕、叠加、响度、成片 | [edit-and-delivery.md](references/edit-and-delivery.md) | `成片/EPxxx.mp4`、`剪辑单.md` | `cut.py`；成片再跑一遍 ASR 对全集台词 |

## 每次执行

1. `project_tool.py status` 看全貌，`next` 定位阶段；读 `项目开发/决策记录.md` 和上一集的 `[连续性]`（三回锚：本批任务、上一批结束状态、当前规则）。
2. 做当前阶段，跑门，修 error；warn 逐条判断后豁免或修。
3. C、E 阶段派 **reviewer 子代理**（没参与写作、`model: opus`）：按参考里的审查问题引用证据写 `审查/<EP>-审查.md`，结论 PASS/REVISE/BLOCKED，每条问题带位置、证据、影响、最小修复，末尾 `keep:` 清单。writer 改完对 keep 清单做字面比对。同一 Major 两轮没过：按 reviewer 的修订建议直接改并记未决，不停。
4. 生产阶段先跑金丝雀镜头，通过再放行整集；每镜起始帧目检、视频 ASR、接触表看图，按自动重拍决策表处置；take 用尽标 weak 进剪辑。
5. 每集出成片后：`project_tool.py status`，把决策、未决、weak 镜写进决策记录；继续下一集。
6. 全部集完成后汇报：每集时长、镜数、重拍次数、weak/drop 镜、未决项、决策记录摘要。

## 自动决策（不问人）

缺什么按 pipeline-contract §8 的默认补：6 集、每集 120 秒、16:9、每镜 5 秒、`qwen21` 1K 起始帧、`fasth3` 768p 视频、take 上限 3、ASR 通过线 0.6。主爽点类型判不出就选智斗复仇。写不出"反派失去什么"的集并入下一集或补小兑现。成片超长先删同向重复反应镜再收出点，不删兑现镜。

## 修改纪律

- 改一拍，连读三拍：改过的镜头前后各一镜一起重读边界链（G26）。
- 修门只改诊断出的那一项；不往提示词里堆负面词。
- 台词只能在剧本阶段改；分镜和提示词阶段发现台词装不下，回剧本合并同质节拍或拆镜。
- 语速：`drama.json` 的 `speech_rates` 是估算值，第一集 ASR 出来后用实测（词级时间）校准，写回配置。

## 续跑与中止

所有脚本已有产物就跳过，中断后重跑同一命令。`STOP` 文件当前任务做完后停；`DEADLINE=YYYYmmddHHMM` 到点不再提交。任务号在 `脚本/ids.log` / `jobs.jsonl`，被杀后 `h3_client.py collect` 收回。

## 深挖时读的本地套件

本 skill 的参考是压缩版；某个问题要更完整的方法时读原文（不必加载全部）：`short-drama-develop/references/`（story-craft、episode-design、mechanism-loop、premise-devices、commercial-payoff-craft、genre-cards）、`short-drama-write/references/`（script-craft、dialogue-craft）、`short-drama-storyboard/references/`（keyframe-craft、blocking-playbooks）、`short-drama-video-prompts/references/minimax-h3.md`、`short-drama-review/references/`（rubric-story-script、production-quality-gates）。五个外部仓库见 README 的来源表。

## 安装维护

`python3 scripts/selftest.py`：起假中转把整条链离线跑一遍（16 项）。需要 ffmpeg/ffprobe、Pillow、requests；有 faster-whisper 环境时顺带测 ASR。
