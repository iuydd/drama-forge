---
name: drama-forge
description: DramaForge：开发、改编、制作、审查与续做 AI 短剧或漫剧，包括剧本、分镜、生成、剪辑和 drama.json 项目续跑。在授权预算内自动推进制作，分别报告制作验收、声音验证和观众反馈；不承诺无人验收的商业效果。
license: MIT
---

# DramaForge

目标只有一个：**观众从头看到尾，看得懂、想看下去、挑不出低级错**。所有流程、门和记录都为这个目标服务；门全过但片子看不懂，就是没做完。

## 1. 先记住这次是怎么失败的（2026-09-27 EP001）

60 镜、所有机械门和审查全过，用户看片：第 2 镜就像换了场景（五人饭桌切成两人中景，身后全是空椅子）；台词前后接不上，看不出在演什么；三只手、同一人出现两次、身子穿过桌子。原因不是模型，是流程：

1. 写剧本时没人问"观众第一次看，懂不懂"；原著里有前因的短台词被单独搬上来。
2. 分镜为了"人脸大"把一场多人戏拆成互不相连的小镜头，每个反打里其他在场的人都消失了。
3. 审片只看缩小的网格接触表，就签了"无硬伤"。

下面的规则就是针对这三点，优先于 references 里任何条文。

## 2. 五条硬规则

1. **看得懂第一。** 剧本和分镜各做一次"盲看复述"：派一个没看过原著和剧本的子代理，只给它分镜的画面描述+台词（按镜序），让它复述剧情、说出主角的处境和装置规则。复述错了或说"看不懂"就回去改，不许进入下一阶段。
   - 开场 30 秒内观众必须知道：主角是谁、在哪、核心设定（装置/能力）是什么、她要什么。设定靠一个能看见的事件交代（例：她心里一句话响起→全家同时停手→有人小声确认"你也听见了？"），不靠字幕卡堆背景。
   - 每句台词单独拿出来要么自己能懂，要么前一两镜已给出前因。原著里靠上下文才成立的台词，补前因或删掉。
2. **一场戏是一个空间。** 每场先有一个交代全员位置的主镜头；之后的镜头都从这个空间里取，**在场的人要么在画里，要么清楚地在画外某侧**（过肩、前景背影、后景虚焦都算在画里）。禁止出现"在场的人突然不见了、只剩空椅子"的镜头。多人饭桌戏以三人/过肩构图为主，单人近景只用于关键反应。
3. **少镜头、长镜头。** 一集 2–3 分钟，15–30 镜为宜。一镜一件事，镜内把动作和反应演完；不要为了机械门或景别把一段连贯的戏切碎。
4. **审片看原图，一帧一帧数。** 每条视频用 `frame_dump.py` 按每秒一帧导出单张图，逐张看，每镜写：几个人（有没有同一人出现两次）、每只手属于谁（有没有多手）、身体有没有穿过桌椅门、在场的人有没有凭空消失、有没有出字。网格接触表只能用来找可疑处，**不能用来放行**。另派一个独立子代理看同一批帧只找这四类硬伤，两边都过才放行。
5. **粗剪要从头到尾看一遍再交。** 交付前按时间线看完整粗剪，用三句话复述剧情；复述不出，或某处"突然换场景/台词莫名其妙"，回到出问题的阶段改，不把粗剪当成品交给用户。

## 3. 不能碰的底线

- **授权只来自用户原话**，记在 `项目开发/决策记录.md`。生成模型、档位、分辨率由用户指定，不自选、不擅自换（详见 [rules-detail.md](references/rules-detail.md) 硬约束 1b）。
- **付费接口（fal、可灵等）每一批提交都要用户点头**；本地 h3studio 不花钱，可直接跑。并发永远开到最大（用户 2026-09-27："并行永远是最多"）：云端一批全提，本地按 `/api/status` 的槽位数。
- **密钥只进环境变量**，不写文件、日志、git、回复。
- **全自动不弹权限**：不写 `rm` 配变量/通配符（用 `/usr/bin/trash` 字面路径）、不写前台 `sleep` 链、不用 curl/wget（用 python requests）。
- **画面不出字**：字幕、清单、面板都后期叠加；模型烧进画面的字要处理掉（重出或局部模糊，模糊后用 `ledger_tool.py derive` 记账）。
- **不删产物**：重出开新 take，旧的留着。
- **如实汇报**：没看的写没看，没听的写未听审；花费取脚本数字。模型听不到声音，听感只由真人签。

## 4. 流程

| 阶段 | 产出 | 过关条件 |
|---|---|---|
| A0 原著拆解（改编才有） | `项目开发/原著分析/`、`改编契约.md` | 逐章抽取 + 独立审查一轮；见 [adaptation.md](references/adaptation.md) |
| A 立项 / B 情绪集纲 | `系列简报.md`、`情绪集纲.md` | 独立审查一轮 |
| C 剧本 | `EPxxx/剧本.md` | `screenplay_lint` 0 error；独立审查一轮；**盲看复述通过**（规则 1） |
| D 视觉设定 | `视觉设定.md`、`参考图/refs.json` | 每个场景一张平面图 + 每人座位/站位；独立审查一轮 |
| E 分镜 | `shots.json` | `shots_tool check` 0 error；**盲看复述通过**；逐场检查规则 2（每镜写出在场者谁在画里、谁在画外哪侧） |
| F 参考图 / G 起始帧 | `参考图/`、`起始帧/` | 逐张看原图写观察并 `mark --frame-take`；同场并排比背景 |
| G2 预演 | `审查/EPxxx-预演.*` | 按时间线看完，复述剧情 |
| H 视频 | `视频/` | 用户授权的模型与批次 |
| I 审片 | `review.json` | 规则 4：逐帧原图 + 独立子代理，两边都过 |
| J 剪辑 / 成片终验 | `成片/`、`审查/EPxxx-成片终验.md` | 规则 5：通看复述；`final_qa.py` |

审查规矩：写的人不审自己写的；每个阶段 reviewer 只审一轮、只拦会让观众看错看不懂的问题（Blocker、剧情事实 Major），其余写"建议"；修完由主会话核对。同一镜出两次硬伤就换一种模型画得出的拍法（少人、少手、改插入镜），不原样重抽。先把第一集做到成片，再动后面的集。

## 5. 常用命令

```bash
S=<本目录>/scripts
python3 $S/project_tool.py init <项目> --title 剧名 --episodes N --dialogue-lang zh
python3 $S/project_tool.py next <项目>                 # 下一步该做什么
python3 $S/isolated_agent.sh <项目> <任务书> worker|reviewer|light|adversary
python3 $S/produce.py refs|frames|videos <项目> [EP] [SID ...] [--retake] [--jobs N]
python3 $S/review_tool.py animatic|sheets|asr|motion|mark <项目> <EP> ...
python3 $S/frame_dump.py <项目> <EP> [SID ...]         # 审片逐帧原图
python3 $S/ledger_tool.py derive <项目> --src … --out … --note …   # 后处理过的视频记账
python3 $S/cut.py <项目> <EP> [--draft]
python3 $S/final_qa.py <项目> <EP>
```

环境：`H3_API`（或 drama.json `api_base`）、`H3_STUDIO_TOKEN`、`FAL_KEY`，只放环境变量；ASR 用 `ASR_PY`。

## 6. 需要细节时再读

| 问题 | 读 |
|---|---|
| 旧版全部条文（授权、门、攻防、声音三项、必拍事实…） | [rules-detail.md](references/rules-detail.md) |
| 文件结构、字段、机械门 G00–G54 | [pipeline-contract.md](references/pipeline-contract.md) |
| 剧本写法 | [screenplay.md](references/screenplay.md)、[story-engine.md](references/story-engine.md) |
| 分镜、调度、轴线 | [storyboard-keyframes.md](references/storyboard-keyframes.md) |
| 图片/视频提示词 | [image-prompts.md](references/image-prompts.md)、[video-prompts-general.md](references/video-prompts-general.md)、[video-prompts-h3.md](references/video-prompts-h3.md) |
| 生成通道（h3studio、fal、可灵） | [providers.md](references/providers.md) |
| 实拍踩过的错 E1–E40 | [production-and-review.md](references/production-and-review.md) |
| 剪辑、字幕、交付 | [edit-and-delivery.md](references/edit-and-delivery.md) |
| 各阶段审查问题 | [review-checklists.md](references/review-checklists.md) |
| 哪个环节用哪个模型 | [model-routing.md](references/model-routing.md) |
| 改编、立项、题材 | [adaptation.md](references/adaptation.md)、[premise-novelty.md](references/premise-novelty.md)、[genre-cards/索引.md](references/genre-cards/索引.md) |

改规则：只改本 skill（仓库 iuydd/drama-forge），`python3 scripts/selftest.py` 通过后提交推送，再同步到 `~/.claude/skills/drama-forge`。
