# 流水线契约

全自动流水线的"账本"：目录、ID、每个阶段的输入产出与门、自动决策规则、续跑方式。所有脚本和 SKILL.md 都以本文件为准。

## 目录

1. 目录布局
2. ID 与命名
3. 阶段表（A–J，含 G2 预演粗剪）
4. `shots.json` 字段
5. `参考图/refs.json` 字段
6. `审查/<EP>-review.json` 字段
7. 机械门 G00–G49
8. 自动决策规则
9. 续跑、中止与收回
10. 硬约束
11. 来源（2026-09-25 调研补充的条目）

## 1. 目录布局

```text
<剧>/
  drama.json                      配置（schema short-drama-autopilot/drama/v1）
  项目开发/系列简报.md 情绪集纲.md 决策记录.md 模型观察.md（只收实测的模型行为，带样本数）
  项目开发/跨集记忆.md             长篇/续季才有（series-long-form §5，模板 assets/templates/跨集记忆.md）
  项目开发/改编契约.md  原著分析/    改编项目才有（adaptation §3、§6；原著分析/ 下是章节索引、逐章提取、聚合与判定）
  项目开发/原稿/<EP>-原稿.*         用户给的现成剧本原稿，规范化前原样留档（screenplay §1b）
  输入/                            改编项目的原始材料（小说、多集原稿），只读；novel_index.py / episode_intake.py 按行号 + sha256 索引
  参考图/refs.json  IMG-*.png       身份图、底板、道具图（全剧共用）
  EP001/剧本.md 视觉设定.md shots.json 分镜.md 图片提示词.md 视频提示词.md 剪辑单.md
  EP001/起始帧/F_<sid>_t<n>.png   视频/V_<sid>_t<n>.mp4   配音/   成片/EP001.mp4
  EP001/成片/EP001.overlays.json   cut.py 写的成片元数据（schema drama-forge/overlays/v1，字段见 §6 末尾），final_qa.py 读它；草剪写在 审查/<EP>-草剪.overlays.json
  审查/<EP>-审查.md               reviewer 子代理的剧本/分镜审查（写作阶段；格式与分级见 review-checklists §0，骨架 assets/templates/审查.md，review_md_check.py 查结构）
  审查/<EP>-grade.json             可选：逐镜接镜调色参数（hub_tool.py grade，edit-and-delivery §5b），输出 成片/<EP>_graded.mp4
  审查/<EP>-sheets/<sid>_t<n>.jpg  接触表（2 帧/秒）
  审查/<EP>-asr.json <EP>-review.json <EP>-审片.md
  审查/<EP>-预演.mp4 <EP>-预演.jpg     预演粗剪（按计划取用时长、带临时对白草音或字幕、标动作起止与反应拍）和 1fps 接触表（review_tool.py animatic）
  审查/<EP>-预演.md                 animatic 生成（首行「结论：待填…」+ `预演指纹：…` + 自动统计 + 逐镜表），模型看完预演把首行改成「结论：PASS / REVISE」，并按模板 assets/templates/预演.md 在下面补逐条答案；不是 PASS 不进阶段 H（project_tool next、produce.py all 都查首行）；指纹行不删——预演内容没变时重跑保留已填结论，变了重出模板、旧文件挪到 <EP>-预演.prev.md
  审查/<EP>-预演-temp/              预演临时读稿（本地 TTS，文件名带 _temp），只听节奏，不进成片
  审查/<EP>-final-qa.json <EP>-final-qa.md   final_qa.py 从最终 MP4 写的机读终验（文字排版、台词与字幕逐句比对、声音测量、片尾）；md 首行「结论：PASS / REVISE」由脚本判，重跑会覆盖，不手改（edit-and-delivery §7b）
  审查/<EP>-final-qa/               终验证据帧与接触表 contact.jpg
  审查/<EP>-成片终验.md             模型写的成片终验结论（模板 assets/templates/成片终验.md）：必拍事实看图、脚本结果汇总、已知问题与用户确认；首行「结论：PASS / REVISE」是阶段 J 的完成标准
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
| A0 原著拆解（仅改编项目） | 小说、网文、多集原稿 | `项目开发/原著分析/`、`项目开发/改编契约.md` | 章节/分集索引 verify 通过；抽样自称抽样；改编契约的不可改事实逐条落集或标延后（adaptation §4–6） | 索引对不上 → 重建索引后再分析 | reviewer 按 review-checklists §R 无 Blocker |
| A 立项 | 点子/一句话/参考 | `项目开发/系列简报.md`（含 `## 立项候选`、`## 爽感打分`）、`drama.json` | 模板方括号全部填掉；`## 立项候选` ≥6 行、两两机制不同、每行写钩子/兑现方式/新在哪里（用了饱和设定时必填）；`## 爽感打分` 在且 ★ 项无 0 分、总分达开工线（premise-novelty §6–7）；主爽点类型只一个；装置条款有 ID | 缺项按 §8 默认补；候选不足或打分不过 → 回 premise-novelty 重出候选 | `project_tool.py next` 不再指向 A，且不再报立项 warn |
| B 情绪集纲 | 系列简报 | `项目开发/情绪集纲.md`（每集一行） | 每格具体；反派失去格非空；交接事实非空 | 写不出反派失去 → 并集或补小兑现 | 每集一行齐 |
| C 剧本 | 集纲那一行 + 前集交接 | `EPxxx/剧本.md` | 格式可解析（`screenplay_lint.py` 无 error）；对白行数 ≥ 镜数下限；reviewer 子代理按 review-checklists §A–C 审剧情逻辑（知情时机、证据链、装置条款） | 按审查 Major 改，最多两轮 | 审查无 Major |
| D 视觉设定 | 剧本 | `EPxxx/视觉设定.md`、`参考图/refs.json` 增量 | 剧本里每个说话人/地点都有条目；每个人物有身份图条目 | 补条目 | 门通过 |
| E 分镜与提示词 | 剧本 + 视觉设定 + refs | `EPxxx/shots.json` → render 三份 md | `shots_tool.py check` 0 error | 修 error；warn 逐条判断，豁免写 `waive` | 0 error |
| F 参考图 | refs.json | `参考图/IMG-*.png` | 模型目检：身份、服装、无字、单人、正面全身 | `produce.py refs --retake` 最多 3 次 | 全部通过目检 |
| G 起始帧 | shots.json + 参考图 | `起始帧/F_*_t*.png` | 模型逐张目检：一人、朝向、持物、构图留空、无字、身份像参考图 | `--retake`，最多 max_takes | 每镜有通过的 take，`review.json` 记 frame_take |
| G2 预演粗剪 | 通过的起始帧 + shots.json 镜序与计划取用 + 台词表 + 情绪集纲 | `审查/<EP>-预演.mp4`（带临时对白草音或字幕、动作起止与反应拍标记）、`<EP>-预演.jpg`、`<EP>-预演.md` | 模型按时间看完逐条答：情节点看得到/只靠台词/看不到；每条 `must_show` 在哪一镜第几秒看得到（只靠台词不算过）；对白说不完就切、重要信息后缺反应拍、只说不做的段落；能力规则是否重复解释（G48 口径）；相邻镜景别角度主体至少变一项；回溯镜同构图；总长与 `target_seconds` 的差（production-and-review §3b） | 有"看不到"、必拍事实只靠台词或复述不出 → 回 E 改分镜或回 G 重出起始帧 | `<EP>-预演.md` 首行「结论：PASS」（脚本查首行，结论由模型判）、下面有逐条答案，预演片存在；金丝雀一镜之外的视频都在这之后提交 [社区][自测] |
| H 视频 | 起始帧与提示词 | 视频 take | ASR 差异提供线索，仍需听审 | 授权范围内诊断后重拍 | 有候选素材 |
| I 审片 | 视频、接触表、听审 | 每 take assessment/edit/verdict、每镜 `must_show_check`、声音三项 | visual/audio/continuity 通过且指纹有效；`must_show_check` 无 fail（脚本强制）、无 unverified（审片人核掉，脚本只显示"未验证"）；`asr_ok` / `listen_ok` / `sync_ok` 分开记，null 如实为"未验证" | 必拍事实 fail → 重拍、改分镜或回剧本，不许以"台词能解释/观众数不出来"放行（production-and-review §5c） | 详见 [质量契约](quality-contract.md) |
| J 剪辑 | review.json + shots.json | `成片/EPxxx.mp4`、`成片/EPxxx.overlays.json`、`剪辑单.md`、`审查/<EP>-final-qa.json`、`<EP>-final-qa.md`、`<EP>-成片终验.md` | 删镜/改剪点前做因果自检（edit-and-delivery §2d，G46 查承担镜仍在 cut_order）；时长在目标 ±30%；响度 −16 LUFS；`ai_label` 有值时前 3 秒可见 AI 生成标识，剪辑单记"AI 标识：有/无（理由）"；成片终验逐项验必拍事实、文字排版（数字专名不断行、不压脸眼、长文字分屏）、台词边界（入点不切进台词或语气词、字幕 = 成片可听内容）、切点、片尾无拖尾停帧、声音三项（edit-and-delivery §7b） | 超长 → 回 I 收紧取用；过短 → 记录、不硬凑；终验不过 → 排版类改叠加重出成片，台词边界类放宽剪点或回剧本，剧情事实类回生产 | 成片存在，`final_qa.py` 已对交付文件跑过（`final-qa.md` 首行 PASS，退出码 0），且 `成片终验.md` 首行「结论：PASS」；或 `成片终验.md` 写「结论：REVISE」并列明已知问题与用户确认（剧情事实类缺陷不能靠用户确认放行） |

写作阶段（A0–E）可以多集并行；生产阶段（F–H，含 G2）全项目串行，一次只有一个任务在飞。G2 不花生成的钱，只用已有起始帧和临时对白拼片。

## 4. `shots.json` 字段

```jsonc
{
  "schema": "short-drama-autopilot/shots/v1",
  "episode": "EP001",
  "notes": ["本集拍法说明，写进分镜.md 开头"],
  "cut_order": ["EP001-S01", "EP001-S02"], // 可选：叙述/剪辑顺序；省略镜须有 drop 理由或作为已审音源
  "scenes": [{"id": "EP001-SC001", "axis": "谁面朝画左/画右", "plates": ["IMG-PLATE-..."],
              "must_show": [{"id": "MS1", "fact": "箱内正好十件，上五下五", "shots": ["EP002-S05"], "kind": "count"}],
                                        // 必拍事实（storyboard-keyframes §2e，来自剧本该场 [连续性] 的「必拍：」）：每场 3–5 条，只看画面也必须读到；
                                        // kind = count | action | state | loss | identity；id 在本集唯一；shots 是计划承担镜（G46 查存在、G47 查数量写进起始帧）
              "waive": []}],             // 场级豁免，目前只认 G49
  "shots": [{
    "id": "EP001-S01", "scene": "EP001-SC001", "title": "中文短标题",
    "kind": "person",                 // person | hands | feet | object | insert | plate | empty
    "must_show_ids": ["MS1"],          // 本镜承担哪些必拍事实；每条 must_show 至少一镜承担且该镜在 cut_order 里，否则 G46 error
    "explains_ability": false,         // 本镜在解释/确认能力规则；同集超过 2 镜或 12 秒、第二集起开头 30 秒内超过 1 镜报 G48（screenplay §5b3）
    "critical_terms": ["素手で"],       // 可选：本镜关键能力词、金额等必须听对的词；cut.py 折行不拆，final_qa.py 识别分歧单列「需母语者确认」
    "duty": "这一镜的戏剧职责（情绪步骤：受气/底牌/反击/押注/兑现/新问题）",
    "script_anchor": ["剧本原句"],     // 承载了剧本哪几句
    "subject": "遥", "facing": "left", // left | right | camera；同场同人必须一致，改向写 axis_break + 理由
    "gaze": {"target": "三上", "direction": "left"},   // 有台词的人物镜必写（G43）：看谁、看画面哪一侧（left | right | camera | down | up）；
                                       // 正反打时 = 本镜 facing、与对手在本场的 facing 相反；起始帧与视频提示词都写出视线方向（storyboard-keyframes §4）
    "gaze_reason": "",                  // 看镜头、看物件、回避视线、目标不是同场人物时写剧情理由（独白、盯着证物说话）
    "split_reason": "",                 // 与上一镜同场同一人物相邻时，为什么必须拆成两镜（景别/机位明显变化、时间跳跃）；不写就默认合并成长镜头（G45）
    "fast_cut_reason": "",              // 插入/冲击镜、反应镜计划取用短于 1.5 秒的理由（G42，storyboard-keyframes §7c）
    "framing": "中近景，谁在哪，面朝哪",
    "keyframe": "冻结关键帧（中文）：位置、朝向、持物、表情、构图留空",
    "frame_prompt": "英文起始帧提示词，顺序同 storyboard-keyframes §6：镜头句 → 主体与动作 → 尺度锚点 → 参考图分工 → The scene is set … → Style: …；必含一镜一人句和 no text；有 frame_parent 时，The same shot as Picture 1 保留句放在镜头句之前",
    "frame_profile": "qwen21", "frame_refs": ["IMG-PLATE-...", "IMG-HARUKA"],   // Picture 1、Picture 2 的顺序；默认 2 张、接触镜 3 张、不超过 3 张（含父帧，G38）；中近景及更近绑头肩图 IMG-<NAME>-FACE，不和全身图同绑
    "frame_parent": "EP001-S02",       // 可选：同机位派生。同场同一人物反复回到同一机位（正反打来回切、回溯镜复刻原镜）时，写该机位第一次通过的镜 ID；
                                       // produce.py 把父镜通过的起始帧作 Picture 1 挂在 frame_refs 前面（Picture 编号顺延），frame_prompt 开头写
                                       // "The same shot as Picture 1: keep the camera position, framing, background and lighting; change only: …"；父镜不存在或在本镜之后报 G40 [社区][自测]
    "motion": "中文动作链：起点 → 唯一动作 → 台词时点 → 终点",
    "video_prompt": "H3 三段：integrated_multimodal_description: … \\noverall_soundscape: … \\nnon_diegetic_music: N/A；台词写 <d>[Japanese] …</d>",
    "video_profile": "base50_sol",      // 可选，默认 drama.json（H3 用）
    "planned_action_window": [1.0, 3.5], // 仅生成前计划；实测区间通过 mark 写当前 take 的 assessment
    "seconds": 5,
    "dialogue": [{"speaker":"遥","text":"逐字等于剧本","lang":"ja","at":0.5,"emotion":"冷静·中·慢·中",
                  "reading": {"三上": "みかみ"}}],   // 对白与动作按表演选择并行或先后；at 仅是计划；lang 必须 = drama.json dialogue_lang（外语台词写 lang_reason）；
                                                    // reading：本句专名/易读错汉字的读音（假名/拼音），配音前按它校对，ASR 读错即不合格（G44，production-and-review §10）
                                                    // 可选配音上下文：to 对谁说（人物名，可多个）、knows 说话人此刻知道/不知道什么、tactic 这句的策略（质问/试探/收回…）；
                                                    // 上一句谁说由镜序推出不另存；只供配音与听审，不改台词、不进 video_prompt，门不检查（production-and-review §10）
    "setup_for": ["空箱"],               // 可选：本镜为哪些人物/物件/事件铺垫来处（起因镜，storyboard-keyframes §2b）
    "requires_setup": ["老师", "EP001-S12"],   // 本镜第一次让观众看到的人物/物件/事件；每项是前面某镜 setup_for 里的名字，或直接写铺垫镜 ID；铺垫不存在或在本镜之后报 G32；
                                       // 事件镜（登场、摔落、冲突爆发、受伤、闯入）必写，指向起因镜；起因就在本镜里先发生写本镜 ID（G32，storyboard-keyframes §2c）
    "reaction_first": false, "silent_reason": "",   // 晚开口 / 无台词的理由
    "end_state": "终点画面", "sound": "环境声与关键音效",
    "sfx": [{"file": "音效/impact.wav", "at": 2.4, "gain_db": 0}],   // 关键动作音效，at 是源素材秒；sound 里写到的关键音效都要落成 sfx
    "overlay": [{"kind": "stamp", "side": "L", "name": "stamp", "phrase": "回るよ", "at": null},   // phrase：只在那一小句说完时亮（ASR 词对齐）
                {"kind": "text", "text": "后期字", "at": 1.0, "until": 3.0},
                {"kind": "panel", "text": "面板内容", "title": "SYSTEM"}],   // panel 样式在 drama.json overlays.panel；单条可覆盖 title/theme/position/width/accent/icon
    "audio_from": [{"shot": "EP005-S07", "at": 0.5, "filter": "phone", "tail": 1.1}],   // 从别的镜垫录音
    "seedance_task": "reference",        // 仅 video_dialect 为 seedance-2.5：reference | edit | extend，默认 reference（video-prompts-seedance §4）
    "continuation_pending": false,       // 仅 Seedance 续接：上一镜未生成或未过审时标 true，保留正文草案、不提交（video-prompts-seedance §5）
    "visual_deps": ["人物「遥」", "地点「会议室」"], "continuity": ["笔在桌上"],
    "multi_person": false, "multi_person_reason": "",   // 接触动作（推、撞、抢、递、扶）必须 true，理由写"接触动作：谁对谁做了什么"
    "boundary": {"start": {"position": "", "facing": "left", "gaze": "", "hands": "", "held": "", "state": ""},
                 "end":   {"position": "", "facing": "left", "gaze": "", "hands": "", "held": "", "state": ""}},   // 边界链（G26 逐项比对）
    "boundary_break": "",               // 同场同主体相邻镜边界不接时的镜外说明
    "video_body": "", "soundscape": "", "music": "",   // 可代替 video_prompt：只写正文，`shots_tool.py build` 拼三段骨架
    "waive": ["G05"]                    // 明确豁免的 warn 门
  }],
  // 尺度锚点不是单独字段：写在 frame_prompt 里（中景以上、双人镜必写人物与护栏/门/桌/台阶的关系，多人写相对身高），
  // 身份图 prompt 写厘米身高，底板 prompt 写至少一个现实尺寸参照（visual-assets §12，G34）；
  // 提示词写必要变化；环境运动按需，明确需要时设 environment_motion_required 与 environment_motion。
  "locks": [{"id": "LOCK-BLAZER", "phrase": "charcoal grey blazer", "subject": "遥", "shots": "all"}]   // 连续性锁（G23）
}
```

### `drama.json` 里和风格相关的字段

```jsonc
"style_preset": "live_modern",   // 七选一：live_modern | live_period | live_xianxia | anime_cel | guoman_3d | manhwa | cg_realistic（references/styles.md）；全剧锁定一种；缺失或不在表里报 G33
"style": "Candid 35mm film still …",  // 风格句，从 styles.md 对应一节整句复制；身份图、底板、起始帧共用
"video_prompt_head": "integrated_multimodal_description: [Shot 1] …"   // 视频头句 + 视频保持句，按画风从 styles.md §1 的表里选，全剧不变；非真人画风不用 handheld、realistic human behaviour（G36）
```

### `drama.json` 里其他新增字段

```jsonc
"ai_label": null,          // 成片前 3 秒右上角叠的 AI 生成显式标识，cut.py 自动叠并记进剪辑单；只在海外发行写 null，理由写决策记录；缺这个键报 G39 [官方]
"line_max": {"zh": 15, "ja": 20, "en": 10},  // 单句上限：zh/ja 按可发声字数，en 按词；超了报 G37，拆成两句、中间插对方反应（screenplay §4"短"，为的是句数多、反应快）
"shot_seconds": {"default": 5, "min": 4, "max": 15},   // H3 duration 4–15 整数秒；同一个人的连续戏合并成长镜头，上限取 max（旧项目的 max 10 按需改大，改动记决策记录）
"pace": {"dialogue_min": 2.5, "dialogue_tail": 0.8, "reaction_min": 1.5, "insert_min": 1.5, "scene_avg_min": 2.5},   // 节奏下限（G42、cut.py 剪辑单）；只设下限
"gate_limits": {"ability_explain_shots": 2, "ability_explain_seconds": 12, "recap_window": 30, "recap_explain_shots": 1,
                "talk_only_ratio": 0.5, "talk_only_min_shots": 3},   // 可选，缺省即此值：G48 能力解释上限与跨集开头窗口、G49 只说不做比例
"readings": {"夏樹": "なつき", "売上": "うりあげ"},   // 全剧专名读音；ASR 比对按它归一，配音前按它校对（单句读音写 dialogue[].reading）；cut.py 折行时把这些词当整体不拆，final_qa.py 把它们当关键词核对
"final_qa": {"asr_min": 0.8},  // 可选：成片终验逐句识别召回下限（final_qa.py --asr-min 可临时覆盖）
"overlays": {"stamp": {…},
             "panel": {"theme": "tech", "accent": [0, 229, 255], "position": "top_left", "width": 0.36, "title": "SYSTEM",
                       "enter": 0.32, "enter_mode": "scale", "type_cps": 22, "glass": true, "glow": 16, "scanlines": true,
                       "hologram": true, "sfx": true, "sfx_file": null, "sfx_gain_db": -10}}
                       // 系统面板样式：主题 tech / xianxia / scroll（styles.md §12），其余键覆盖主题默认；字段说明 edit-and-delivery §4
```

`video_dialect`：视频提示词方言，`minimax-h3`（默认）| `seedance-2.0` | `seedance-2.5`；只在用户指定模型后改，按它只读一份方言文件（video-prompts-general 开头）。当前门脚本 G09/G10/G17/G44 与 `produce.py` 只认 H3 写法，用 Seedance 的暂行做法见 video-prompts-seedance §7；官方接口通道用 `providers.py`（providers.md）。

`project_tool.py init … --style-preset live_xianxia` 写入 `style_preset`；换 preset 时 `style` 句也要按 styles.md 那一节换。

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

转面板与裁格（image-prompts §3.3）：转面板条目加 `"layout": "multi_view"`，只作目检与裁格来源，不直接挂进起始帧 `frame_refs`；从板上裁出的单格另登记（如 `IMG-<NAME>-BACK`，`refs: ["IMG-<NAME>-SHEET"]`），写 `"crop_from": "IMG-<NAME>-SHEET"`。这两个键目前只由 `visual_lint.py`（V01、V02、V06）读取，`check-refs` 不认识，转面板可能收到 G18 的"建议全身/正面" warn，按转面板豁免并记决策记录。

头肩身份图 `IMG-<NAME>-FACE`：有台词的主要人物做一张，以全身身份图为唯一参考图派生（`refs: ["IMG-<NAME>"]`，同一个 `subject`），头顶到上胸、脸约占画高一半；不写 `voice`。check-refs 对它免"建议全身"和"写身高"两条 warn，同一 `subject` 的全身图与头肩图之间不比 G20 雷同（visual-assets §3）。

身份图：素背景、正面、全身、中性表情、**不带以后要消失的饰品**（金表、戒指会跟着人物走）、**写厘米身高**（`about 168 cm tall`）。底板：无人、无字、说明画左画右各是什么、**写至少一个现实尺寸参照**（`a standard 2.1 m door`、`handrails about 1 m high`），空间说得通（门后不接门、楼梯方向与剧本一致、窗外景与楼层一致，visual-assets §4b）。

## 6. `审查/<EP>-review.json` 字段

审片结构与 CLI 以 [quality-contract.md](quality-contract.md) 为准。旧顶层 in/out/mode/speed 不再用于正式剪辑；须对当前 take 重审。

```jsonc
{"episode":"EP001","shots":{"EP001-S01":{
  "frame_take":2,"video_take":1,"verdict":"pending_review","locked":false,
  "must_show_check":{"MS1":"pass"},      // 镜级镜像：mark --must-show 同时写进当前 take 和这里；读的时候以 take 级为准，镜级只在它属于当前 video_take 时才算
  "video_takes":{"1":{
    "heard":"识别文本", "speech_diff":{"status":"needs_listening"},
    "edit":{"mode":"fixed","in":0.3,"out":4.6,"speed":1},
    "assessment":{"checks":{…},"evidence":{…},
                  "asr_ok":true,"listen_ok":null,"sync_ok":null},   // 声音三项：识别正确 / 听感自然 / 口型同步；null = 未验证，报告显示「未验证」，不得汇总成"通过"
    "must_show_check":{"MS1":"pass"},    // 本镜 must_show_ids 逐条 pass|fail|unverified；有 fail：mark 拒绝 ok/weak，auto 给 retake，choose_best 不选，正式剪辑拒绝
    "verdict":"pending_review"
  }}
}},
 "final_qa":{"asr_ok":null,"listen_ok":true,"sync_ok":true,"evidence":"谁、在成片哪几秒听/看了什么"}}
                                         // 可选：成片终验的人工补验；必须带非空 evidence，final_qa.py 才用它覆盖脚本给不出的 null
```

声音三项在 take 的 `assessment` 里，用 `review_tool.py mark … --asr-ok true|false|null --listen-ok … --sync-ok …` 写；必拍事实用 `--must-show MS1=pass|fail|unverified`（可重复）。入剪只要求 `asr_ok` 为 true；`listen_ok` 或 `sync_ok` 为 false 时拦下，为 null 时放行但审片报告、剪辑单、终验处处显示"未验证"。旧记录只有 `checks.audio` 时：`pass` 只算 `asr_ok: true`（旧"audio pass"实际只是 ASR 通过），`fail` 算 `asr_ok: false`，`listen_ok` / `sync_ok` 一律 null，绝不从旧字段推成通过。`must_show_check` 的 `unverified` 脚本目前不拦剪（只显示"未验证"），审片规则仍要求承担镜在正式剪辑前核成 pass（production-and-review §5）。

用 mark 完成检查后脚本写入 assessment 的 checks、evidence、media_sha256、shot_sha256、reviewed_at、speed 及实测窗口。不可复制示例证据或假装已听审。`must_show_check` 与声音三项的判定规则见 production-and-review §5、§5c。

`成片/<EP>.overlays.json`（cut.py 写，schema `drama-forge/overlays/v1`）：`duration`；`segments[]` 每段镜号、take、成片起止、取用 in/out、台词边界注记（入点前移/出点后移）、字幕裁剪警告；`overlays[]` 每条叠字的种类（字幕/后期字/面板/印章字）、时段、文字、实际渲染的行 `lines`、不可拆词 `protected`、位置 `rect` / `position`、人脸检查结果、警告。重剪就重写；final_qa.py 发现它记录的片长与成片差超过 0.5 秒报 error。

`审查/<EP>-final-qa.json`（final_qa.py 写）：`schema`、`episode`、`video`、`video_sha256`、`duration`、`conclusion`（PASS / REVISE）、`asr_ok` / `listen_ok` / `sync_ok`（脚本只能给 `asr_ok`；另两项为 null，除非 review.json 顶层 `final_qa` 带 evidence 写入）、`manual`（用了哪些人工值）、`asr_min`、`issues[]`（`t`、`end`、`type`、`severity` = error / warn / confirm、`detail`、`evidence` 证据帧）、`text`（叠字数、断行、超两行未分屏、压脸、人脸检查状态）、`speech`（逐句字幕原文、听到的内容、问题）、`audio`（LUFS、LRA、峰值、削波、片尾静止/静音、流时长）、`contact_sheet`。必拍事实看图、已知问题和用户确认不在这里，写 `审查/<EP>-成片终验.md`（edit-and-delivery §7b）。

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
| G16 | warn | 粗估时长区间与动作段检查；对白密度/前 3 拍/连说提示仅用于 commercial_fast 或显式配置 |
| G17 | warn | 视频正文（`<d>` 外）出现人名；H3 用 the man / (S1) 指代 |
| G18 | error/warn | 参考图提示词英文、含 no text；身份图一个人、全身、正面、无饰品、有 subject |
| G19 | error/warn | 底板 No people、写清左右；道具图 no hands、白底、尺度 |
| G20 | error | 两张身份图提示词相似度 ≥ 75%（观众会认错人） |
| G21 | warn | 说话人的音色描述（refs.json `voice`）没逐字进 video_prompt |
| G22 | warn | 提示词里留了分支（or / 或者 / 可选） |
| G23 | error / warn | 连续性锁（`locks[].phrase`）没有逐字进范围内的起始帧提示词（error）；也没有逐字进该镜 `video_prompt` / `video_body`（台词 `<d>…</d>` 不算，warn） |
| G24 | error | 关键帧、终点、动作、边界里出现回指词（同上 / 与上一镜相同 / same as previous） |
| G25 | warn | 同场两个人物朝向相同，正反打不互补 |
| G26 | error | 同场同主体相邻镜的边界链不接（前一镜 `boundary.end` ≠ 本镜 `boundary.start`），无 `boundary_break` |
| G27 | warn | 同场同主体同景别（跳切）；紧挨着且没写 `split_reason` 的由 G45 提示合并，不重复报 |
| G28 | error | 同场用了两块以上底板，派生底板没在 refs.json 的 `refs` 里挂同场主底板（各自独立生成，切镜像换了地方） |
| G29 | warn | 动作职责镜缺动作计划或预留时间可能不足；计划不能直接作为剪辑实测 |
| G30 | warn | 全景/全身/远景人物镜配了台词（脸只有几十像素，口型和表情读不出；对白镜至少中近景，脸高 ≥ 画高 1/5） |
| G31 | warn | 有台词却没写 `dialogue[].emotion`（情绪·强度·语速·音量）；配音会平读 |
| G32 | warn | `requires_setup` 的铺垫不成立：写成名字的，没有任何镜在 `setup_for` 里铺垫，或铺垫镜在本镜之后；写成镜头 ID 的，该镜不存在或在本镜之后（人物/物件凭空出现；写本镜 ID 表示起因在本镜内）。另：`title`/`duty` 写了事件（登场、摔、撞、闯入、受伤、爆发……）却既没 `requires_setup` 也没 `setup_for`（事件没交代起因） |
| G33 | warn | `drama.json` 没写 `style_preset`，或不在风格库七个值里 |
| G34 | warn | 尺度锚点缺失：身份图没写身高；底板没写现实尺寸参照；绑了底板的中景以上/双人人物镜，起始帧没写人物与护栏/门/桌/台阶的关系或相对身高 |
| G35 | warn | environment_motion_required 为 true 但未提供具体 environment_motion；不做关键词猜测 |
| G41 | error/warn | `cut_order` 为空、重复或含未知镜头报 error；同场 scene_state 的已声明持久事实在后续镜头无因跳变（含跨主体反打）报 warn |
| G36 | warn | 画风漂移诱因：`anime_cel` / `manhwa` 的起始帧出现焦段（35mm）、bokeh、cinematic lighting、volumetric、4k、photorealistic、film grain、depth of field；`guoman_3d` 出现 photograph、photorealistic、film grain；非真人、非 `cg_realistic` 画风的 `video_prompt_head` 含 handheld、realistic human。否定式（no film grain）不算（styles.md §1、storyboard-keyframes §6b 第 8 项）[社区] |
| G37 | warn | 剧本单句超过 `line_max`（默认 zh 15 字、ja 20 字、en 10 词）；拆成两句、中间插对方反应或动作，不删台词（screenplay §4）[社区][自测] |
| G38 | warn | 起始帧参考图（`frame_refs` + 父帧）超过 3 张；同一人物的全身图和头肩图同绑；中近景/近景/特写绑了全身图而 refs.json 里有该人物的 `-FACE`（visual-assets §3、§8）[官方][社区] |
| G39 | warn | `drama.json` 没写 `ai_label`：默认写 null（不叠标识）；只有用户明确要求才写文字（用户 2026-09-26 定：没让加就不加） |
| G40 | error/warn | `frame_parent` 指向不存在或在本镜之后的镜报 error；指向不同场或不同主体的镜报 warn（同机位派生只用于同场同一人物）[社区] |
| G42 | warn | 节奏下限：对白镜计划取用 < max(2.5s, 台词说完 + 0.8s)；反应镜 < 1.5s 或插入镜 < 1.5s 且没写 `fast_cut_reason`；同场计划平均镜长 < 2.5s（`drama.json pace`，storyboard-keyframes §7c）。计划取用 = motion/duty/continuity 里"取用约 X 秒"，没写按整条 `seconds` [自测] |
| G43 | warn | 视线：有台词的人物镜没写 `gaze`；`gaze.direction` 与本镜 `facing` 矛盾，或与对手在本场的 `facing` 同向（两人看同一侧）；看镜头 / 目标不是同场人物却没写 `gaze_reason`；起始帧或视频提示词没写视线方向或方向不一致；提示词让人物看镜头（否定式 nobody looks at the camera 不算）（storyboard-keyframes §4）[自测] |
| G44 | warn | 台词语种与读音：`dialogue[].lang` ≠ `dialogue_lang` 且无 `lang_reason`；`<d>[语种]` 标签与 `dialogue_lang` 不符；日语台词一个假名都没有（像中文）、中文台词混入假名；日语台词里的汉字专名（剧本人物名）没有 `dialogue[].reading` 也不在 `readings`（screenplay §4c、production-and-review §10）[自测] |
| G45 | warn | 同一人不拆两镜：同场相邻两镜主体相同、中间没有别人的镜头或插入镜，且后一镜没写 `split_reason`；默认合并成一个长镜头，时长按内容定、上限 `shot_seconds.max`（storyboard-keyframes §7b）[自测] |
| G46 | error/warn | 必拍事实（storyboard-keyframes §2e）：`scenes[].must_show` 条目缺 id/fact、id 重复、`shots` 指向不存在的镜、镜头 `must_show_ids` 里有未登记的 id、某条事实没有任何镜的 `must_show_ids` 承担、承担镜全部不在 `cut_order` 里（删镜删掉了因果证据）报 error；`kind` 不在五类里、`shots` 列了某镜而该镜 `must_show_ids` 没写这条报 warn [自测：外部审查] |
| G47 | warn | 数量事实：`kind: count` 的承担镜 `frame_prompt` 没写出事实里的数字（阿拉伯数字，或跟量词的中文数字如「十件」「五份」，接受英文数词 ten/five）；事实里没有可解析的数字时，frame_prompt 至少要有一个数字（storyboard-keyframes §6b 道具布局镜）[自测：外部审查] |
| G48 | warn | 能力规则重复解释：同集（按 cut_order）`explains_ability` 镜超过 `gate_limits.ability_explain_shots`（默认 2）或计划取用合计超过 `ability_explain_seconds`（默认 12 秒）；第二集起开头 `recap_window`（默认 30 秒）内超过 `recap_explain_shots`（默认 1）镜（screenplay §5b3）[自测：外部审查] |
| G49 | warn | 只说不做：同场有台词的人物镜（不含 audio_from、不在 cut_order 的）≥ `talk_only_min_shots`（默认 3）且超过 `talk_only_ratio`（默认一半）的 motion 里没有承接对方行为的动作或反应词（夺、合上、推回、后退、僵住……）；有意保持不动的镜写 `waive: ["G49"]`，整场豁免写在 scene 的 `waive`（storyboard-keyframes §8c）[自测：外部审查] |

`shots_tool.py check-refs` 跑 G18–G20 和 G34 的参考图部分；其余在 `check`。预演粗剪（阶段 G2）和成片终验（阶段 J）不是编号门：`project_tool.py next` 和 `produce.py all` 检查 `审查/<EP>-预演.md` 存在且首行是「结论：PASS」；成片终验看 `审查/<EP>-final-qa.md` 首行（edit-and-delivery §7b）。逐条答案由模型判，不过就写「结论：REVISE」，不许写 PASS 放行。G31–G49 里的 warn：写作者判断后可豁免，但豁免理由要写进决策记录；它们挡的是"没写"，写得对不对由目检（production-and-review §4b 细节与比例清单、§10 听感）和 reviewer 判。每次 check 追加 `脚本/gates.jsonl`（哪些门响了），无人值守时靠它看哪条规则最常被违反。

error 必须清零；warn 逐条判断，明确豁免写在 shot 的 `waive`。门只能证明"没犯这些错"，不能证明戏好；戏好坏由 reviewer 子代理按 [review-checklists.md](review-checklists.md) 判。

非编号的格式检查（只读，不进 G 编号、不写 gates.jsonl）：`screenplay_lint.py`（SP，剧本格式，screenplay §1）、`visual_lint.py`（V01–V06，参考图与起始帧提示词，image-prompts）、`review_md_check.py`（RV，审查文件结构，review-checklists §0.3–0.4）。有 error 时退出码 1，按同样的规矩修到 0 error、warn 逐条判断。

## 8. 自动决策规则

无人值守时不问人，按下表拍板并写进 `项目开发/决策记录.md`：

| 缺什么 | 默认 | 备注 |
|---|---|---|
| 集数 | 6 | 单集约 2 分钟 |
| 单集目标时长 | 120 秒 | `target_seconds` |
| 选哪个点子 | 按 premise-novelty §6 出 ≥6 个机制不同的候选，按 §7 快筛取最高分，同分取更新颖的；用户给了点子则它算一个候选 | 饱和设定可以用，但必须带新内容，候选表写清新在哪里（只换皮不算）；用户点名要的照做，同样写清新在哪里；用户在场要看点子时给前三名由用户挑 |
| 主爽点类型 | 从点子判断，只选一个 | 判不出选"智斗复仇" |
| 画风 `style_preset` | 按题材从 styles.md §1 选，全剧一种 | 判不出选 `live_modern` |
| 台词语言 | 点子里的语言，否则中文 | `dialogue_lang` |
| 画幅 | 16:9 | 平台明确竖屏才 9:16 |
| 每镜秒数 | 按内容定：单一动作或一句台词约 5 秒；同一个人连续做事、连说两句合并成一个长镜头（常见 8–10 秒），上限 `shot_seconds.max`（H3 15 秒） | G04 算容量；G45 提示没合并的同人相邻镜；G42 查下限 |
| 同一人相邻两镜 | 合并成一个长镜头 | 只有景别/机位明显变化、插入他人或物件、时间跳跃才拆，写 `split_reason` |
| 说话人视线 | 看着对手，方向与对手在画面上的位置一致，不看镜头 | 独白、回避、看物件写 `gaze_reason` |
| 系统面板样式 | `overlays.panel.theme` 按画风选（styles.md §12），判不出用 `tech` | 全剧一种主题 |
| TTS 语言与参考音频 | 语言参数 = `dialogue_lang`；参考音频是同语言母语者的对话口吻录音 | 不用"自动检测"；没有母语者参考音频时先停下列候选（硬约束 1b 的同类情况） |
| 生成模型/档位/分辨率（视频、图片、TTS、对口型） | 用 `drama.json` 中用户定的值；缺失时停下问用户，不自选（列 2–3 个候选和价格交用户定） | 新项目 profiles 初始为 null；历史案例不代表当前用户已定。模型和尺寸明确前不生产（SKILL.md 硬约束 1b） |
| take 上限 | 3 | `budget.max_takes` |
| ASR 准入 | 不用数值通过线；差异须听审，一致也需声音/画面/连续性审查 | 旧 budget.asr_pass 仅兼容读取，不参与审批/自动重拍 |
| 起始帧目检不过 | 重拍到上限，仍不过 → 改提示词（只改失败的那一项）再拍 | 记决策；有底板的镜头不许用水平镜像代替重出；细节与比例清单（production-and-review §4b）任何一项不过都算不过 |
| 底板空间说不通 | 重出底板（提示词按平面图写空间事实），再重出受影响的起始帧 | 门后接门、楼梯方向反、窗外与楼层不符都算，不因"只是背景"放过 |
| 因果或披露缺口 | 区分世界原因、角色认知和观众所知 | 有意隐藏记揭示计划；需要预先披露才用 requires_setup |
| 配音平 | 按 `emotion` 换情绪参考或 instruct 重生成该句 | 听感五问（含口音与句尾语调）不过即重生成（production-and-review §10） |
| 同场背景对不上 | 先查底板是否派生（G28）并成对目检；底板不对重出派生底板，再重出该场受影响的起始帧 | 不因"画质"重拍，但换了地方是剧情问题，要重拍 |
| 视频 take 用尽仍有问题 | 关键缺陷阻止正式成片；非关键瑕疵且审查通过才接受 weak | 写 acceptance_reason；变速后重新听审 |
| 无台词镜出现人声 | 重拍一次，仍有 → verdict=mute | 剪辑去原声 |
| 成片超长 | 先删同向重复反应镜，再收紧出点 | 不删兑现镜 |
| 剧本审查两轮后仍有 Major | 按 reviewer 的修订建议直接改，记录未决 | 不停下等人 |
| 可生成性预算 | 每集有台词的角色 ≤ 4、首场有名有姓的人物 ≤ 3；每集主场景 ≤ 3（多出的复用底板）；接触同框镜每场 ≤ 3（超限改剧情、减少接触动作，不把多出的接触拆成单人镜凑数）；不写要多人同框才读得懂的群戏；金手指文字走后期叠加 | 立项写进系列简报，超了先改点子（story-engine §1）；豁免记决策 |
| 预演不过 | 回 E 改分镜（换景别、补起因镜、回溯镜复刻原镜、补承接动作），或回 G 重出那几镜起始帧，再拼一次预演 | 不因"视频也许会动起来"放行（production-and-review §3b） |
| 必拍事实没成立（数量错、关键动作没拍出、反派损失没落到画面） | 重拍；两次不过改分镜（换承担镜、拆插入镜、双人同框）；仍不行回剧本改这条事实并同步台词和下游引用 | 不许以"台词能解释/观众数不出来"放行，不许用延长镜头、旁白、字幕替代（production-and-review §5c） |
| 能力规则讲了不止一次 | 保留讲清的那一次，其余改成一句提醒或删掉；跨集开头只留 ≤5 秒回顾 | G48；改动写决策记录（screenplay §5b3） |
| 成片终验不过 | 排版类改叠加参数重出成片；台词边界类放宽剪点或回剧本删句重出字幕；片尾停帧收紧叠字时长；剧情事实类回生产 | 交付前必须有 `final-qa.md`；有已知问题写 REVISE 并取得用户确认（edit-and-delivery §7b） |
| 起始帧参考图 | 默认 2 张（底板 + 身份），接触同框 3 张，不超过 3 张 | 中近景以上绑 `-FACE`；同机位反复出现用 `frame_parent` |
| AI 生成标识 | `ai_label: null`（默认不叠） | 用户明确要求才写文字，cut.py 叠在前 3 秒右上角 |
| 新的模型行为结论 | 先记 `项目开发/模型观察.md`（观察、N 次里几次、能判断什么、混杂因素） | 同一写法有效 ≥ 3 次才升级成 skill references 里的规则；单次改善只记录 [社区][推断] |
| API 连不上 | 写作阶段照做；生产阶段停，写明原因 | 其他停止条件包括未决提交、预算边界与 STOP/DEADLINE，见 runtime-boundaries.md |

## 9. 续跑、中止与收回

- 已有产物通常跳过；中断后先核对账本，未决提交必须先 reconcile，不能盲目重跑；`project_tool.py next` 告诉你下一步。
- 每次提交立刻写 `脚本/ids.log`（人读）和 `脚本/jobs.jsonl`（机读）；进程被杀后先 `h3_client.py collect --job <id> --kind video --out <路径>` 收回，不重发 POST。
- `STOP` 文件：当前任务做完后停；`DEADLINE=YYYYmmddHHMM`：到点不再提交。
- 只重试 GET；POST 响应未知会阻止后续提交。提交前 intent 刷盘，按[运行边界与恢复](runtime-boundaries.md)对账后 collect 或确认未受理。

## 10. 硬约束

1. token 只从环境变量 `H3_STUDIO_TOKEN` 读；不写进文件、日志、提交、回复。
2. 串行：一次只提交一个生成任务；`/api/status` 空闲才提交。
3. 接触关系与前后状态可读；双人镜、手部特写或有证据的省略按叙事选择。
4. 镜长按内容定：同一个人的连续戏合并成一个长镜头（上限 `shot_seconds.max`），对白长的镜按容量加长而不是加快语速；成片不低于节奏下限（`pace`）。
5. 生成画面里不出任何字；字幕、面板、印章字全部后期叠加；手机屏幕背对镜头。
6. 台词逐字等于剧本；剧本和 shots.json 漂移由 G09/G10 挡。
7. 能力规则/装置条款先改系列简报再进剧本；剧中不得先写出契约里没有的能力。
8. 在用户已授权范围内连续执行，常规决定写入决策记录；模型/档位/尺寸缺失、触及预算、STOP/DEADLINE、提交结果未知或真实创作分叉时暂停依赖工作。具体边界见 runtime-boundaries.md。
9. 维持项目画风、物理空间与角色状态。世界内因果成立，观众获知顺序服从叙事；环境运动按需。详见 scene-state-and-reveal.md 与 quality-contract.md。
10. 视频提交前必过预演粗剪（阶段 G2，带临时对白与节奏标记）；预演按 shots.json 镜序拼，不调换先后。
11. 台词是目标语言母语者的日常口语；配音语言参数、参考音频语言都等于台词语言；专名按 reading 校对（screenplay §4c、production-and-review §10）。
12. 每个事件交代起因、每个关键物品交代来源（storyboard-keyframes §2c）；说话人看着说话对象（§4）；系统面板走 `overlays.panel` 样式（styles.md §12）。
13. 必拍事实不可妥协（storyboard-keyframes §2e、production-and-review §5c）；每集交付前从最终 MP4 做成片终验（edit-and-delivery §7b）；声音结论分 `asr_ok` / `listen_ok` / `sync_ok` 三项如实写，未验证不写成通过。

## 11. 来源（2026-09-25 调研补充的条目）

- 静帧预演：国内 AI 短剧工作流教程把"分镜规划与预演"单列一步 https://juejin.cn/post/7680825116924362758 ；BigBanana-AI-Director 的批量生成前计划预审 https://github.com/shuyu-labs/BigBanana-AI-Director （只借思路）
- 同机位父帧派生：HKUDS/ViMax `agents/camera_image_generator.py` 的机位树 https://github.com/HKUDS/ViMax
- 模型观察表与升级门槛：zenstory-ai/drama-skills `evaluations/model-behavior-probes.md` https://github.com/zenstory-ai/drama-skills
- AI 生成显式标识：《人工智能生成合成内容标识办法》https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm
- 可生成性预算：飞书 OpenClaw 漫剧流程的选题五维 https://www.feishu.cn/content/article/7643731845971987667
- 画风漂移诱因词、头肩身份图、参考图数量、单句长度：分别见 styles.md、visual-assets.md、screenplay.md 文末来源
- G46–G49、预演粗剪、成片终验、声音三项：2026-09-26 用户转来的外部深度审查（7 个成片、235 个剪辑镜头；鉴宝 EP002 道具数量与认输表演、谎话 EP002 金额断行遮脸、挨拳 EP001 入点切进语气词与能力重复解释）[自测]
- G42–G45、面板样式、台词本地化与配音口音、事件起因：2026-09-26 用户看完「按一下回到十秒前」EP001 后的反馈（`按一下回到十秒前/审查/EP001-复盘.md`：日语配音口音、镜头 1–2 秒一切、空箱凭空出现）[自测]
