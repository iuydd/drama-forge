# 爆剧引擎 / DramaForge

**中文** · [English](README.en.md)

一个给 AI 编码 agent（Claude Code、Codex 等）用的 skill：从一个点子无人值守地做出一部商业爽剧短剧。

**它把目前网上能找到的短剧 skill 全部拆开读完、逐条提炼精华，再合成一条能跑的流水线。**六套来源：short-drama 十一件套、shuohao-skills、su-ai-short-drama、cinematic-video-prompt-engineer、director、AI-drama-pound；每一套都通读过全部文件、实际跑过它们的脚本和自测，只留下对全自动商业爽剧真正有用的方法，并写成 27 道能机械执行的门。各家取了什么见下面的[来源表](#精华来自哪里)。

```text
点子 → 系列简报（四问 + 主爽点类型 + 装置条款）→ 情绪集纲（每集：受气 / 底牌 / 反击 / 反派失去 / 兑现 / 新问题）
→ 剧本 → 视觉设定 + 参考图 → 分镜与冻结关键帧（shots.json）→ 起始帧 → 视频 → ASR / 接触表 / 看图三层审片
→ 自动重拍 → 剪辑（字幕、叠字、响度）→ 成片
```

设计取向：剧情比画质重要；台词要多、反应要快；一个镜头只拍一个人；生成画面里不出字，字全部后期叠加；写作阶段可并行，生产阶段全项目串行；所有替人拍的板都写进决策记录。

## 安装

```bash
git clone https://github.com/iuydd/drama-forge.git ~/.agents/skills/drama-forge
ln -s ~/.agents/skills/drama-forge ~/.claude/skills/drama-forge   # Claude Code
python3 ~/.agents/skills/drama-forge/scripts/selftest.py          # 离线自测，起一个假的生成中转把整条链跑一遍
```

依赖：Python ≥ 3.10、`requests`、`Pillow`、ffmpeg/ffprobe。审片的 ASR 用 `faster-whisper`（可装在单独的 venv 里，用环境变量 `ASR_PY` 指向那个 python）。

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
S=~/.agents/skills/drama-forge/scripts
python3 $S/project_tool.py init <项目目录> --title "剧名" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 $S/project_tool.py next <项目目录>      # 下一步该做什么
```

然后在 agent 里说「用 drama-forge 从这个点子全自动做一部短剧」。阶段、门、命令见 `SKILL.md`，字段与规则见 `references/pipeline-contract.md`。

已有项目中的 `short-drama-autopilot/*/v1` schema 标识继续有效；改名不改变项目数据格式。

## 结构

```text
SKILL.md                      入口：硬约束、阶段表 A–J、自动决策、修改纪律
references/
  pipeline-contract.md        目录、ID、shots.json / refs.json / review.json 字段、27 道机械门、默认表
  story-engine.md             商业爽剧剧情：四问、主爽点类型、冲突引擎、装置条款、情绪集纲、兑现五要素、信息权限表
  screenplay.md               剧本格式、场景发动机、台词多快有用途、时长与容量、审阅格式
  visual-assets.md            视觉设定、身份图/底板/道具、连续性锁、参考图权限、文字政策
  storyboard-keyframes.md     一镜一人、轴线记账、正反打配对、边界链、冻结关键帧配方、切点节奏
  video-prompts-h3.md         H3 三段方言、口型与一镜一人、对白预算、表演层、运镜、可生成性改写
  production-and-review.md    生产纪律、金丝雀、目检清单、三层审片、自动重拍决策表、取用区间
  edit-and-delivery.md        出点规则、字幕、叠加、声音、响度、交付核对
scripts/
  project_tool.py             init / status / next
  shots_tool.py               check（G00–G27）/ check-refs / render / build / coverage
  produce.py                  refs / frames / videos / all（串行、跳过已有、take、ASR 自动重拍）
  review_tool.py              sheets / asr / auto / report / mark
  cut.py                      ffmpeg 剪辑：取用、字幕、叠字、印章字、录音垫入、环境声、响度
  h3_client.py                生成中转客户端：串行、账本、先收回再重投、落盘校验、STOP / DEADLINE
  common.py · selftest.py
assets/
  drama.template.json         项目配置模板
  refs.template.json          参考图清单模板
  templates/                  系列简报、情绪集纲、决策记录
  example/                    一个合成的示例集（selftest 用）
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

## 许可

MIT，见 `LICENSE`。
