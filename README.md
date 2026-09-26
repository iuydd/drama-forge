# 爆剧引擎 / DramaForge

**中文** · [English](README.en.md)

一个给 AI 编码 agent（Claude Code、Codex 等）用的 skill：从一个点子无人值守地做出一部商业爽剧短剧。

**它把目前网上能找到的短剧 skill 全部拆开读完、逐条提炼精华，再合成一条能跑的流水线。**六套来源：short-drama 十一件套、shuohao-skills、su-ai-short-drama、cinematic-video-prompt-engineer、director、AI-drama-pound；每一套都通读过全部文件、实际跑过它们的脚本和自测，只留下对全自动商业爽剧真正有用的方法，并写成 G00–G49 这些能机械执行的门。short-drama 十一件套的全部内容已并入本 skill，现在只需要安装 drama-forge 一个 skill。各家取了什么见下面的[来源表](#精华来自哪里)。

```text
点子（或小说 / 现成多集原稿 → 原著拆解 + 改编契约）→ 系列简报（四问 + 主爽点类型 + 装置条款）→ 情绪集纲（每集：受气 / 底牌 / 反击 / 反派失去 / 兑现 / 新问题）
→ 剧本 → 视觉设定 + 参考图 → 分镜与冻结关键帧（shots.json）→ 起始帧 → 预演粗剪（带临时对白和节奏标记，视频花钱前先看懂没有）→ 视频
→ ASR / 接触表 / 看图三层审片（逐镜核必拍事实）→ 自动重拍 → 剪辑（字幕、叠字、响度、AI 生成标识）→ 成片 → 成片终验
```

设计取向：剧情比画质重要；台词要多、反应要快；一个镜头只拍一个人；生成画面里不出字，字全部后期叠加；写作阶段可并行，生产阶段全项目串行；所有替人拍的板都写进决策记录。

## 安装

```bash
git clone https://github.com/iuydd/drama-forge.git ~/.agents/skills/drama-forge
ln -s ~/.agents/skills/drama-forge ~/.claude/skills/drama-forge   # Claude Code
python3 ~/.agents/skills/drama-forge/scripts/selftest.py          # 离线自测，起一个假的生成中转把整条链跑一遍
```

依赖：Python ≥ 3.10、`requests`、`Pillow`、ffmpeg/ffprobe。审片的 ASR 用 `faster-whisper`（可装在单独的 venv 里，用环境变量 `ASR_PY` 指向那个 python）。

安装路径按宿主环境选择，上面的 `.agents` / `.claude` 只是 Claude 环境示例，下载目录可直接使用。离线自测默认不运行 ASR；已缓存模型后显式设 `SELFTEST_ASR=1` 才启用。只有提交/恢复检查时运行 `python3 scripts/client_selftest.py`。

新建项目不预选生成模型：在 `drama.json.profiles` 中填写当前项目已确认的模型/档位与尺寸后再生产。底层 CLI 的 `--profile`、`--res` 必填。响应未知时先对账，见[运行边界与恢复](references/runtime-boundaries.md)。

## 生成接口

脚本假设有一个自建的 MiniMax H3 中转，地址由环境变量 `H3_API`（或 `drama.json` 的 `api_base`）给出，token 只从环境变量 `H3_STUDIO_TOKEN` 读。接口约定见 `scripts/h3_client.py`：

| 接口 | 用途 |
|---|---|
| `GET /api/status` | `running` / `queued`，空闲才提交 |
| `POST /api/v1/image` | `{prompt, profile, aspect, res, seed, images[data-uri…]}` → `{id}` |
| `POST /api/v1/generate` | `{prompt, profile, aspect, res, seconds, seed, image_mode: "keyframe", images[首帧]}` → `{id}` |
| `GET /api/jobs/{id}` | `status: done / failed …` |
| `GET /api/jobs/{id}/image` `/video` | 下载 |

换别的生成服务只需改 `h3_client.py` 的四个方法；其余脚本只认「提交 → 任务号入账 → 轮询 → 收回」这条契约。

## 快速开始

```bash
S="/actual/skill/path/drama-forge/scripts"
python3 "$S/project_tool.py" init <项目目录> --title "剧名" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 "$S/project_tool.py" next <项目目录>      # 下一步该做什么
```

然后在 agent 里说「用 drama-forge 从这个点子全自动做一部短剧」。阶段、门、命令见 `SKILL.md`，字段与规则见 `references/pipeline-contract.md`。

已有项目中的 `short-drama-autopilot/*/v1` schema 标识继续有效；改名不改变项目数据格式。

## 结构

```text
SKILL.md                      入口：硬约束、阶段表 A0–J（含 G2 预演粗剪、J 成片终验）、自动决策、修改纪律、按需深读索引
references/
  pipeline-contract.md        目录、ID、shots.json / refs.json / review.json 字段、机械门 G00–G49、非编号格式检查、默认表
  runtime-boundaries.md       授权范围、成本边界、提交结果未知时的对账与恢复
  market-hits.md              市场爆款题材库（平台、形态、金手指长青度）
  premise-novelty.md          点子新颖度与爽感打分、立项候选
  story-engine.md             商业爽剧剧情：四问、主爽点类型、冲突引擎、装置条款、情绪集纲、兑现五要素、信息权限
  genre-cards/                题材卡：索引（跨题材比较、开场入口、钩子、制作难点）+ 12 张题材卡
  series-long-form.md         长篇连载与续季：前史与切入、驱动力、弧线压力测试、跨集记忆、分集卡
  adaptation.md               改编：A0 原著拆解管道、多集原稿接入、改编契约（删线、合并、换载体）、对标只学机制
  screenplay.md               剧本格式与规范化、每场必拍事实、场景发动机、台词多快有用途、本地化、事件起因、能力只讲一次、分遍修订与续写
  visual-assets.md            视觉设定：身份与变体、地点与视图、道具状态、声音方向、连续性锁与变化记录、参考图权限
  image-prompts.md            参考图提示词：身份图、转面板、底板、道具、状态变体、局部编辑、模型差异
  scene-state-and-reveal.md   三本账（世界事实、角色认知、观众认知）、揭示保护、跨正反打状态
  storyboard-keyframes.md     一镜一人、轴线、正反打与视线、边界链、冻结关键帧、一眼看懂、必拍事实、承接对方行为、长镜头合并、节奏下限
  video-prompts-general.md    模型无关的视频提示词通则：节拍、环境动态、表情避坑、接触同框、时序、声音同轨
  video-prompts-h3.md         H3 方言、口型与一镜一人、对白预算、表演层、运镜、可生成性改写
  video-prompts-seedance.md   Seedance 2.0 / 2.5 方言（仅用户指定时）
  providers.md                官方接口通道：MiniMax 视频/语音/配乐、Seedance、GPT Image 2 的参数、限制与收回
  production-and-review.md    生产纪律、金丝雀、目检清单、预演粗剪、三层审片、必拍事实不可妥协、声音三项、自动重拍决策表、配音
  quality-contract.md         审片记录（review.json）的证据与准入
  edit-and-delivery.md        入出点与可用带、删镜因果自检、台词边界、字幕、叠字排版、声音、接镜调色、响度、交付核对、成片终验
  styles.md                   七种画风（style_preset）、制作形态卡、系统面板主题
  review-checklists.md        各阶段审查必答问题、分级、结论与输出格式（A–E、F–J 索引、R/R2 改编、S 长篇）
  project-hub.md              多剧进度总览、导出资料、决策记录与模型观察、规则冲突优先级
  _merge-ledger/              short-drama 十一件套逐文件并入记录（历史台账，运行时不读）
scripts/
  project_tool.py             init / status / next
  shots_tool.py               check（G00–G49）/ check-refs / render / build / coverage
  produce.py                  refs / frames / videos / all（串行、跳过已有、take、ASR、同机位父帧）
  review_tool.py              animatic（预演粗剪）/ sheets / asr / motion / auto / report / mark
  cut.py                      ffmpeg 剪辑：取用（入出点台词保护）、字幕（数字专名不断行、分屏、按实际取用裁剪）、叠字避脸（需 OpenCV）、系统面板、印章字、录音垫入、环境声、响度、节奏统计、AI 标识；写 成片/<EP>.overlays.json
  final_qa.py                 成片终验：从最终 MP4 查文字排版、字幕与成片 ASR 逐句比对、关键词分歧、声音测量、片尾拖尾
  h3_client.py                H3 中转客户端：串行、账本、先收回再重投、落盘校验、STOP / DEADLINE
  providers.py                官方接口适配器（复用同一任务账本；密钥只从环境变量读）
  hub_tool.py                 overview（多剧总览）/ export（导出资料）/ measure（交付测量）/ grade（接镜调色）
  screenplay_lint.py          剧本格式检查（SP）
  visual_lint.py              参考图与起始帧提示词检查（V01–V06）
  review_md_check.py          审查文件结构检查（RV）
  novel_index.py              长篇原著章节索引 index / verify / sample / coverage
  episode_intake.py           多集原稿精确分集 index / manual-index / verify / slice / progress / merge
  review_quality.py           审片证据与剪辑准入的纯函数（被 review_tool / cut 调用）
  common.py
  selftest.py                 整链离线自测（假中转）
  client_selftest.py          提交与恢复自测（不需要 ffmpeg/Pillow）
  quality_selftest.py         语义筛查、take 审片、剪辑准入、场景状态自测
  merged_selftest.py          合并进来的新工具自测（hub_tool、providers、visual_lint、screenplay_lint、review_md_check、novel_index、episode_intake）
  selftest_providers.py       只跑 providers 那一项
assets/
  drama.template.json         项目配置模板
  refs.template.json          参考图清单模板
  templates/                  系列简报、情绪集纲、决策记录、模型观察、剧本、视觉设定、审查、改编契约、跨集记忆
  market/                     市场数据表
  example/                    一个合成的示例集（selftest 用）
```

自测：

```bash
python3 scripts/selftest.py            # 整链（需要 ffmpeg/ffprobe、Pillow、requests；--no-media 跳过媒体）
python3 scripts/client_selftest.py     # 提交与恢复
python3 scripts/quality_selftest.py    # 质量契约
python3 scripts/merged_selftest.py     # 合并进来的新工具；只跑一项：merged_selftest.py <名字>
```

## 精华来自哪里

下表是六套来源各自贡献的精华。本 skill 是对这些公开项目方法的提炼与改写（非逐字复制），以及实战生产脚本的通用化。感谢原作者。

| 项目 | 许可 | 取了什么 |
|---|---|---|
| short-drama 十一件套（develop / write / assets / image-prompts / storyboard / video-prompts / review / edit / produce / novel-analyze / core） | MIT | 四级规则分级、H3 方言与口型实测、连续性锁、冻结关键帧、商业爽剧情绪设计、审片处置与回归表 |
| [eternityspring/shuohao-skills](https://github.com/eternityspring/shuohao-skills) | Apache-2.0 | 门写成代码、爽点间隔门、冷开场认领、台词逐字对账、修改纪律 |
| [doublesq97-ui/su-ai-short-drama](https://github.com/doublesq97-ui/su-ai-short-drama) | MIT | 兑现五要素、对手学习三步、金手指三次节奏、单集七功能、岗位交接契约 |
| [CyberJ0605/cinematic-video-prompt-engineer-skill](https://github.com/CyberJ0605/cinematic-video-prompt-engineer-skill) | MIT | 触发词表情时间轴、两信号预算、情绪保护层、外科修复、运镜与表演模块 |
| [s1dashu/director](https://github.com/s1dashu/director) | MIT | 任务账本纪律、金丝雀镜头、身份图与场景参考的层级 |
| [POUND0423/AI-drama-pound](https://github.com/POUND0423/AI-drama-pound) | MIT | 规则只从失败样本加、审阅带 keep 清单、场次标头一致性 |

2026-09-25 又按一轮网上调研补了几处，只借思路、用自己的话重写：静帧预演门（国内工作室把"分镜预演"单列一步）、同机位父帧派生（[HKUDS/ViMax](https://github.com/HKUDS/ViMax) 的机位树，MIT）、模型观察表与"≥3 次有效才升级成规则"（[zenstory-ai/drama-skills](https://github.com/zenstory-ai/drama-skills) 的行为探针表，MIT）、成片 AI 生成标识（[《人工智能生成合成内容标识办法》](https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm)）。

2026-09-26 按一份外部深度审查（7 个成片、235 个剪辑镜头）收紧了导演执行和成片验收：每场必拍事实 `must_show`（G46 承担镜覆盖、删镜后仍在；G47 数量写进起始帧），能力规则重复解释（G48），对白镜只说不做（G49）；视频前的预演改成带临时对白和节奏标记的粗剪；审片禁止"台词能解释/观众数不出来"放行剧情事实缺陷；每集从最终 MP4 做成片终验（数字专名不断行、叠字不压脸、入点不切进台词、片尾无停帧）；声音结论拆成识别正确、听感自然、同步正确三项，没验证的如实写未验证。

## 许可

MIT，见 `LICENSE`。
