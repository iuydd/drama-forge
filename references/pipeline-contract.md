# 流水线契约

全自动流水线的"账本"：目录、ID、每个阶段的输入产出与门、自动决策规则、续跑方式。所有脚本和 SKILL.md 都以本文件为准。

## 目录

1. 目录布局
2. ID 与命名
3. 阶段表（A–J）
4. `shots.json` 字段
5. `参考图/refs.json` 字段
6. `审查/<EP>-review.json` 字段
7. 机械门 G00–G27
8. 自动决策规则
9. 续跑、中止与收回
10. 硬约束

## 1. 目录布局

```text
<剧>/
  drama.json                      配置（schema short-drama-autopilot/drama/v1）
  项目开发/系列简报.md 情绪集纲.md 决策记录.md
  参考图/refs.json  IMG-*.png       身份图、底板、道具图（全剧共用）
  EP001/剧本.md 视觉设定.md shots.json 分镜.md 图片提示词.md 视频提示词.md 剪辑单.md
  EP001/起始帧/F_<sid>_t<n>.png   视频/V_<sid>_t<n>.mp4   配音/   成片/EP001.mp4
  审查/<EP>-审查.md               reviewer 子代理的剧本/分镜审查（写作阶段）
  审查/<EP>-sheets/<sid>_t<n>.jpg  接触表（2 帧/秒）
  审查/<EP>-asr.json <EP>-review.json <EP>-审片.md
  脚本/ids.log jobs.jsonl asr_cache.json prompts/<EP>/*.txt
  STOP                             出现即停（当前任务做完后）
```

创作真相是 Markdown（剧本、视觉设定、系列简报）和 `shots.json`；分镜.md / 图片提示词.md / 视频提示词.md 由 `shots_tool.py render` 从 `shots.json` 生成，只读不改。

## 2. ID 与命名

| 东西 | 形式 | 例 |
|---|---|---|
| 集 | `EP` + 三位 | `EP001` |
| 场 | 集 + `-SC` + 三位，剧本二级标题 `## EP001-SC001 内 · 地点 · 时间` | `EP001-SC002` |
| 镜头 | 集 + `-S` + 两位 | `EP001-S07` |
| 参考图 | `IMG-` + 大写英文 | `IMG-HARUKA`、`IMG-PLATE-MEETING` |
| 起始帧 | `F_<镜>_t<take>.png` | `F_EP001-S07_t2.png` |
| 视频 | `V_<镜>_t<take>.mp4` | `V_EP001-S07_t1.mp4` |
| 种子 | `crc32(剧名:镜:种类)` 派生 + `(take-1)*1000` + `SEED_OFF` | 可复现，重拍换 take 即换种子 |

take 从 1 起，只增不删；哪个 take 进成片由 `review.json` 决定，默认最新。

## 3. 阶段表

| 阶段 | 输入 | 产出 | 门 | 失败处理 | 完成标准 |
|---|---|---|---|---|---|
| A 立项 | 点子/一句话/参考 | `项目开发/系列简报.md`、`drama.json` | 模板方括号全部填掉；主爽点类型只一个；装置条款有 ID | 缺项按 §8 默认补 | `project_tool.py next` 不再指向 A |
| B 情绪集纲 | 系列简报 | `项目开发/情绪集纲.md`（每集一行） | 每格具体；反派失去格非空；交接事实非空 | 写不出反派失去 → 并集或补小兑现 | 每集一行齐 |
| C 剧本 | 集纲那一行 + 前集交接 | `EPxxx/剧本.md` | 格式可解析；对白行数 ≥ 镜数下限；reviewer 子代理审剧情逻辑（知情时机、证据链、装置条款） | 按审查 Major 改，最多两轮 | 审查无 Major |
| D 视觉设定 | 剧本 | `EPxxx/视觉设定.md`、`参考图/refs.json` 增量 | 剧本里每个说话人/地点都有条目；每个人物有身份图条目 | 补条目 | 门通过 |
| E 分镜与提示词 | 剧本 + 视觉设定 + refs | `EPxxx/shots.json` → render 三份 md | `shots_tool.py check` 0 error | 修 error；warn 逐条判断，豁免写 `waive` | 0 error |
| F 参考图 | refs.json | `参考图/IMG-*.png` | 模型目检：身份、服装、无字、单人、正面全身 | `produce.py refs --retake` 最多 3 次 | 全部通过目检 |
| G 起始帧 | shots.json + 参考图 | `起始帧/F_*_t*.png` | 模型逐张目检：一人、朝向、持物、构图留空、无字、身份像参考图 | `--retake`，最多 max_takes | 每镜有通过的 take，`review.json` 记 frame_take |
| H 视频 | 起始帧 + video_prompt | `视频/V_*_t*.mp4` | ASR 命中 ≥ asr_pass；无台词镜无人声 | `produce.py videos --asr` 自动重拍到 max_takes | 每镜有 take |
| I 审片 | 视频 + 接触表 + ASR | `review.json`（take、in/out、mode、verdict）、`<EP>-审片.md` | 模型看接触表：动作可读、身份一致、方向对、无出字；ASR 命中 | verdict=retake → 回 H；weak → 取可用段或 speed；drop → 剪掉并记录 | 每镜有 verdict |
| J 剪辑 | review.json + shots.json | `成片/EPxxx.mp4`、`剪辑单.md` | 时长在目标 ±30%；响度 −16 LUFS | 超长 → 回 I 收紧取用；过短 → 记录、不硬凑 | 成片存在 |

写作阶段（A–E）可以多集并行；生产阶段（F–H）全项目串行，一次只有一个任务在飞。

## 4. `shots.json` 字段

```jsonc
{
  "schema": "short-drama-autopilot/shots/v1",
  "episode": "EP001",
  "notes": ["本集拍法说明，写进分镜.md 开头"],
  "cut_order": ["EP001-S03", "EP001-S01"],   // 可选：冷开场等非顺序剪法；默认按 shots 顺序
  "scenes": [{"id": "EP001-SC001", "axis": "谁面朝画左/画右", "plates": ["IMG-PLATE-..."]}],
  "shots": [{
    "id": "EP001-S01", "scene": "EP001-SC001", "title": "中文短标题",
    "kind": "person",                 // person | hands | feet | object | insert | plate | empty
    "duty": "这一镜的戏剧职责（情绪步骤：受气/底牌/反击/押注/兑现/新问题）",
    "script_anchor": ["剧本原句"],     // 承载了剧本哪几句
    "subject": "遥", "facing": "left", // left | right | camera；同场同人必须一致，改向写 axis_break + 理由
    "framing": "中近景，谁在哪，面朝哪",
    "keyframe": "冻结关键帧（中文）：位置、朝向、持物、表情、构图留空",
    "frame_prompt": "英文起始帧提示词：主体与动作 → 参考图分工 → The scene is set … → Style: …；必含一镜一人句和 no text",
    "frame_profile": "qwen21", "frame_refs": ["IMG-PLATE-...", "IMG-HARUKA"],   // Picture 1、Picture 2 的顺序
    "motion": "中文动作链：起点 → 唯一动作 → 台词时点 → 终点",
    "video_prompt": "H3 三段：integrated_multimodal_description: … \\noverall_soundscape: … \\nnon_diegetic_music: N/A；台词写 <d>[Japanese] …</d>",
    "video_profile": "fasth3",          // 可选，默认 drama.json
    "seconds": 5,
    "dialogue": [{"speaker": "遥", "text": "逐字等于剧本", "lang": "ja", "at": 0.5}],
    "reaction_first": false, "silent_reason": "",   // 晚开口 / 无台词的理由
    "end_state": "终点画面", "sound": "环境声与关键音效",
    "overlay": [{"kind": "stamp", "side": "L", "name": "stamp", "phrase": "回るよ", "at": null},   // phrase：只在那一小句说完时亮（ASR 词对齐）
                {"kind": "text", "text": "后期字", "at": 1.0, "until": 3.0},
                {"kind": "panel", "text": "面板内容"}],
    "audio_from": [{"shot": "EP005-S07", "at": 0.5, "filter": "phone", "tail": 1.1}],   // 从别的镜垫录音
    "visual_deps": ["人物「遥」", "地点「会议室」"], "continuity": ["笔在桌上"],
    "multi_person": false, "multi_person_reason": "",
    "boundary": {"start": {"position": "", "facing": "left", "gaze": "", "hands": "", "held": "", "state": ""},
                 "end":   {"position": "", "facing": "left", "gaze": "", "hands": "", "held": "", "state": ""}},   // 边界链（G26 逐项比对）
    "boundary_break": "",               // 同场同主体相邻镜边界不接时的镜外说明
    "video_body": "", "soundscape": "", "music": "",   // 可代替 video_prompt：只写正文，`shots_tool.py build` 拼三段骨架
    "waive": ["G05"]                    // 明确豁免的 warn 门
  }],
  "locks": [{"id": "LOCK-BLAZER", "phrase": "charcoal grey blazer", "subject": "遥", "shots": "all"}]   // 连续性锁（G23）
}
```

## 5. `参考图/refs.json` 字段

```jsonc
{"schema": "short-drama-autopilot/refs/v1",
 "refs": {"IMG-HARUKA": {"kind": "identity",        // identity | plate | prop | style
                      "name": "遥 全身身份参考", "subject": "遥",
                      "controls": "脸、发型、体形", "not_controls": "服装、姿势、表情、背景",
                      "voice": "a young woman's calm, clear voice",        // 说话角色固定音色描述（G21）
                      "profile": "krea2_turbo", "res": "2K", "refs": [],   // refs：生成它时要挂的其他参考图
                      "prompt": "Photorealistic full-body photo of one … no text, no logo."}}}
```

身份图：素背景、正面、全身、中性表情、**不带以后要消失的饰品**（金表、戒指会跟着人物走）。底板：无人、无字、说明画左画右各是什么。

## 6. `审查/<EP>-review.json` 字段

```jsonc
{"episode": "EP001", "shots": {"EP001-S01": {
   "frame_take": 2, "video_take": 1,
   "video_takes": {"1": {"hit": 0.83, "heard": "君がいなくても回るよ", "words": [[0.6, 1.1, "君が"]], "duration": 5.0, "stray_voice": false}},
   "verdict": "ok",                 // ok | weak | retake | drop | mute | missing
   "mode": "after_last_word",       // after_last_word | to_end | fixed | full
   "in": 0.3, "out": 4.6, "speed": 1.0,
   "note": "模型看接触表后的判断：动作、身份、方向、出字",
   "locked": true                   // mark 过的镜，auto 不再改
}}}
```

## 7. 机械门

| 门 | 级别 | 判什么 |
|---|---|---|
| G00 | error | 剧本文件不存在 |
| G01 | error | 必填字段、ID 唯一且形如 `EPxxx-Sxx`、场景在剧本里 |
| G02 | error | 人物镜的起始帧提示词含一镜一人句；`multi_person` 必须给理由 |
| G03 | error/warn | 参考图在 refs.json；人物镜绑了身份图；场景底板被绑 |
| G04 | error | 秒数在 [min,max]；台词按语速估时 + 0.5s 收尾装得下；台词有 speaker |
| G05 | warn | 第一句在 `dialogue_start_max` 内开口；人物镜没台词要写 `silent_reason` |
| G06 | error/warn | 起始帧提示词含 `no text`；不出现"reads/written/sign says"一类要求可读文字的写法 |
| G07 | error | 禁词（`forbidden_words`）出现在提示词里（否定式 "no red" 不算） |
| G08 | error/warn | 同场同人朝向一致；人物镜要写 facing |
| G09 | error | 视频提示词含三段键；有台词必有 `<d>`；每句台词逐字在 video_prompt 里 |
| G10 | error | 每句台词逐字在剧本里 |
| G11 | error/warn | 剧本每场有镜头；每句对白有镜头承载（warn） |
| G12 | error | overlay 只能 text/stamp/panel；stamp 必有 side |
| G13 | warn | 关键帧描述 ≥ 20 字；一镜一人句与 two/both/people 同现 |
| G14 | warn | 成片估长偏离目标 30% 以上 |
| G15 | warn | 说话人不在剧本/视觉设定里 |
| G16 | warn | 剧本层：前 3 拍有对白（冷开场）；估时在目标 ±25%；台词秒数占比 ≥ `dialogue_ratio_min`；同一人连说 ≤3 句；每场有动作段 |
| G17 | warn | 视频正文（`<d>` 外）出现人名；H3 用 the man / (S1) 指代 |
| G18 | error/warn | 参考图提示词英文、含 no text；身份图一个人、全身、正面、无饰品、有 subject |
| G19 | error/warn | 底板 No people、写清左右；道具图 no hands、白底、尺度 |
| G20 | error | 两张身份图提示词相似度 ≥ 75%（观众会认错人） |
| G21 | warn | 说话人的音色描述（refs.json `voice`）没逐字进 video_prompt |
| G22 | warn | 提示词里留了分支（or / 或者 / 可选） |
| G23 | error | 连续性锁（`locks[].phrase`）没有逐字进范围内的起始帧提示词 |
| G24 | error | 关键帧、终点、动作、边界里出现回指词（同上 / 与上一镜相同 / same as previous） |
| G25 | warn | 同场两个人物朝向相同，正反打不互补 |
| G26 | error | 同场同主体相邻镜的边界链不接（前一镜 `boundary.end` ≠ 本镜 `boundary.start`），无 `boundary_break` |
| G27 | warn | 同场同主体相邻镜同景别（跳切） |

`shots_tool.py check-refs` 跑 G18–G20；其余在 `check`。每次 check 追加 `脚本/gates.jsonl`（哪些门响了），无人值守时靠它看哪条规则最常被违反。

error 必须清零；warn 逐条判断，明确豁免写在 shot 的 `waive`。门只能证明"没犯这些错"，不能证明戏好；戏好坏由 reviewer 子代理按 `story-engine.md` 和 `screenplay.md` 的审查问题判。

## 8. 自动决策规则

无人值守时不问人，按下表拍板并写进 `项目开发/决策记录.md`：

| 缺什么 | 默认 | 备注 |
|---|---|---|
| 集数 | 6 | 单集约 2 分钟 |
| 单集目标时长 | 120 秒 | `target_seconds` |
| 主爽点类型 | 从点子判断，只选一个 | 判不出选"智斗复仇" |
| 台词语言 | 点子里的语言，否则中文 | `dialogue_lang` |
| 画幅 | 16:9 | 平台明确竖屏才 9:16 |
| 每镜秒数 | 5；对白长的按容量加到 ≤ 8 | G04 算 |
| 起始帧/视频档位 | `qwen21` 1K / `fasth3` 768p | 画质不是现阶段重点 |
| take 上限 | 3 | `budget.max_takes` |
| ASR 通过线 | 0.6（LCS 比例） | `budget.asr_pass` |
| 起始帧目检不过 | 重拍到上限，仍不过 → 改提示词（只改失败的那一项）再拍 | 记决策 |
| 视频 take 用尽仍弱 | verdict=weak，取可用段或 1.2–1.5 倍速 | 不无限重拍 |
| 无台词镜出现人声 | 重拍一次，仍有 → verdict=mute | 剪辑去原声 |
| 成片超长 | 先删同向重复反应镜，再收紧出点 | 不删兑现镜 |
| 剧本审查两轮后仍有 Major | 按 reviewer 的修订建议直接改，记录未决 | 不停下等人 |
| API 连不上 | 写作阶段照做；生产阶段停，写明原因 | 唯一需要人的情况 |

## 9. 续跑、中止与收回

- 每个脚本都"已有产物就跳过"，中断后重跑同一命令即可；`project_tool.py next` 告诉你下一步。
- 每次提交立刻写 `脚本/ids.log`（人读）和 `脚本/jobs.jsonl`（机读）；进程被杀后先 `h3_client.py collect --job <id> --kind video --out <路径>` 收回，不重发 POST。
- `STOP` 文件：当前任务做完后停；`DEADLINE=YYYYmmddHHMM`：到点不再提交。
- 只重试 GET；POST 永不自动重发；网络断开时等待而不是放弃。

## 10. 硬约束

1. token 只从环境变量 `H3_STUDIO_TOKEN` 读；不写进文件、日志、提交、回复。
2. 串行：一次只提交一个生成任务；`/api/status` 空闲才提交。
3. 一个镜头只拍一个人或一双手；多人只能是手/脚/物件插入镜，露第二张脸要 `multi_person_reason`。
4. 每镜生成约 5 秒，成片留 4–5 秒；对白长的镜按容量加长而不是加快语速。
5. 生成画面里不出任何字；字幕、面板、印章字全部后期叠加；手机屏幕背对镜头。
6. 台词逐字等于剧本；剧本和 shots.json 漂移由 G09/G10 挡。
7. 能力规则/装置条款先改系列简报再进剧本；剧中不得先写出契约里没有的能力。
8. 全自动：不用 AskUserQuestion，不停下问人；每个替人拍的板写进决策记录。
