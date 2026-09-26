---
name: drama-forge
description: 爆剧引擎 / DramaForge：短剧与漫剧的一站式全流程技能，从点子、小说或现成剧本无人值守地做出商业爽剧成片。覆盖开发（立项、题材卡、长篇与续季）、改编（原著拆解、多集原稿接入）、剧本写作与修订、视觉资产与参考图提示词、分镜与冻结关键帧、视频提示词（H3、Seedance）、生产（H3 中转与官方接口、配音、配乐）、ASR 审片与自动重拍、剪辑交付，以及各阶段审查与多剧总控。用户要做、续做、改编或审查一部 AI 短剧，或继续已有 drama.json 项目时使用。Use for end-to-end AI short-drama development, writing, visuals, production, review and editing.
license: MIT
---

# 爆剧引擎 / DramaForge

把一个点子做成能追看的商业爽剧成片，在用户已授权的范围和成本边界内连续执行。商业爽剧的密集对白、即时反应和顺叙是本流程的创作预设，当前请求和项目设定优先。

## Quick Start

```bash
S="/实际安装目录/drama-forge/scripts"  # 替换为本 SKILL.md 所在目录下的 scripts
python3 "$S/selftest.py"                                                  # 安装后跑一次，离线
python3 "$S/project_tool.py" init <项目目录> --title "剧名" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 "$S/project_tool.py" next <项目目录>                               # 任何时候：下一步该做什么
```

生产需要环境变量 `H3_API`（你的 H3 中转地址，也可写在 `drama.json` 的 `api_base`）和 `H3_STUDIO_TOKEN`（只从环境读，不落盘）；审片需要 `ASR_PY`（装了 faster-whisper 的 python，例如 `~/.venvs/asr/bin/python`；不设则自动扫 `~/.venvs/*`）。

## 硬约束（一直有效）

1. **有界自动执行**：按[运行边界与恢复](references/runtime-boundaries.md)先明确本轮集数、任务范围、模型/尺寸、提交次数上限及成本边界；已有明确授权直接沿用，范围内连续执行。缺模型配置、触及预算、STOP/DEADLINE、提交结果未知或真实创作分叉时停止依赖工作。常规创作决定写进 `项目开发/决策记录.md`。
1a. **全自动 = 不能弹权限请求**（用户 2026-09-26 定）：主会话和子代理的命令都不能触发权限确认弹窗。禁止 `rm`/`rm -f` 配变量路径或通配符（每次输出到新目录，或字面路径 + `/usr/bin/trash`）、禁止前台 `sleep` 后接命令（用后台任务或 until 循环）、禁止 curl/wget 直连（用 python requests）；遇到会弹窗的写法就换写法。
1b. **模型由用户指定**：生成用的模型、档位、分辨率（视频、图片、TTS、对口型）由用户指定；项目里用户已定的默认（`drama.json` / `项目开发/决策记录.md`）可直接用；用户没指定的，不许自选、不许擅自换，列 2–3 个候选和价格交用户定。新项目 `profiles` 初始为空；模板、技能中的案例和历史项目决定都不构成当前项目授权。
2. **串行**：一次只提交一个生成任务；提交前查 `/api/status` 空闲。POST 永不自动重发；先查账本收回未收回的任务。
3. **镜头服务可读性**：对话可用单人正反打；接触用双人镜、可辨手部特写或有意省略，确保前后归属和因果成立。景别、节拍和长度由叙事及项目模型能力决定，不固定脸部比例或每镜秒数。详见 storyboard-keyframes.md。
4. **生成画面不出字**：字幕、面板、印章字全部后期叠加；手机屏幕背对镜头。
5. **台词逐字等于剧本**（G09/G10）；能力规则/装置条款先改系列简报再进剧本。
6. **剧情优先**：审片只看剧情、动作可读、台词完整、有无出字、有没有认错人；画质不作重拍理由。但**关键情节点的动作没生成出来、方向反了、或被剪在出点之外，是必须处理的问题**（重拍、改取用区间或改分镜），不能用"不重拍"放过；审片必须看接触表，逐镜写出职责动作在原片第几秒发生（production-and-review §5）。
6a. **点子要新、要爽**：立项先出 ≥6 个机制不同的候选、按爽感检查表打分选一；看破谎言、摸物知价、挨打到账、强制说真话、短时回溯、读心、系统面板、重生复仇、赘婿战神退婚、亮令牌等饱和设定可以用，但必须带新内容（新规则/限制、新代价、新视角、新兑现方式、新反制循环、新组合或新世界观/职业承载，至少一项），在候选表写清新在哪里，只换皮不算（[premise-novelty.md](references/premise-novelty.md)）。出候选前先查[市场爆款题材库](references/market-hits.md)，定首发平台与形态，每个候选标注对标的爆款组合与长青度（长青的是能持续升级的金手指，隐藏大佬亮身份型多是昙花一现）。
6b. **开场服从故事**：默认 `opening_mode: story_driven`，先建立可理解的冲突；只有已选异能获得型故事才用 `power_acquisition` 开场。闪回、闪前可以使用，但必须标清时间、视角和信息来源；`cut_order` 遵循剧本的叙述顺序。
6c. **信息可读且不提前泄底**：交代当前理解行动所需的场景与规则；规则可以通过行动、对白或字幕呈现。区分世界事实、角色所知、观众所知；有意隐藏的信息记揭示计划，不强制事先展示全部道具。
6d. **场景连续**（否则一切镜头观众就以为换了地方）：同一场戏所有镜头的背景必须读得出是同一个地方。同场的反打底板必须以主底板为参考图派生（refs.json `refs`，G28），目检底板成对看；起始帧目检把本镜和同场上一镜并排比背景；有底板的镜头禁止水平镜像起始帧。
6e. **画面真实、因果可见、声音有情绪**（六条一起守，出处在括号里）：
   - **风格锁定**：立项在 `drama.json` 选 `style_preset`（真人都市、古装、修仙、日漫、国漫 3D、韩漫、写实 CG 七选一），全剧一句 `style`，不在单集单镜换画风（[styles.md](references/styles.md)，G33）。
   - **比例与细节**：按项目画风和世界设定核对尺度、手形、持物、光源和透视；提示词仅补影响本镜的必要锚点（storyboard-keyframes §6b）。
   - **场景合理**：门后不接门、下楼楼梯不接上楼楼梯、窗外景与楼层一致、走廊通向合理；每个主场景写一行平面图与动线，同场各底板拼得回这张平面图，底板目检必答"空间说不说得通"（visual-assets §4b）。
   - **因果与信息权限**：世界内原因要成立，观众获知顺序按悬念设计；`requires_setup` 仅记录必须预先披露的依赖。跨镜状态与隐藏信息见 [scene-state-and-reveal.md](references/scene-state-and-reveal.md)。
   - **环境动态**：仅在自然存在或承担情节时描述；静止背景本身不构成失败。明确需要运动时填 `environment_motion_required` 与 `environment_motion`（G35）。
   - **台词有情感**：每句台词写 `emotion`（情绪·强度·语速·音量）；配音按情绪选参考音频或用支持 instruct 的 TTS；配音验收在 ASR 之外加听感（情绪对不对、喊叫句有没有力度）（screenplay §4b、production-and-review §10，G31）。
6f. **听得像母语、看得懂、节奏稳**（用户看完 EP001 的反馈："说话语调，口音很奇怪，台词也不本地""镜头切换太快""要完整交代事情，关键物品的来源""系统弹窗做的有科技感一点""人物要看着他说话""事件一定要交代起因""同一个人就不要弄两个镜头"）：
   - **台词本地化与母语口音**：台词是目标语言母语者日常会说的口语（一人称、称谓、敬语层级、语气词、年龄身份口吻），禁止翻译腔和书面腔；reviewer 做母语审读，逐句标不自然处并给改写。配音的语言参数显式等于台词语言，克隆参考音频是同语言母语者的对话录音，专名写 `reading` 并在配音前校对；ASR 读错专名或识别成别的语言即不合格（screenplay §4c、production-and-review §10，G44）。
   - **长镜头与节奏下限**：同一场里相邻两镜主体是同一个人、中间没有别人或插入镜，默认合并成一个长镜头（按内容 8–10 秒常见，上限 `shot_seconds.max`，H3 15 秒），只有景别/机位/剧情明显变化或时间跳跃才拆并写 `split_reason`（G45）。成片对白镜不短于台词说完 + 0.8 秒且 ≥ 2.5 秒、反应镜 ≥ 1.5 秒、插入/冲击镜更短要写 `fast_cut_reason`、同场平均镜长 ≥ 2.5 秒；一句台词在一个镜头里说完（storyboard-keyframes §7b–7c、edit-and-delivery §2，G42）。
   - **一眼看懂**：每个事件（登场、摔落、冲突爆发、受伤、闯入）之前一定有起因（画面、台词或声音），事件镜用 `requires_setup` 指向起因镜；关键物品第一次出现要有来源镜，或清楚的插入特写 + 台词点明；关键事件的起因、经过、结果三拍都要有画面或台词；reviewer 和静帧预演必答"只看画面加字幕，每个关键物品/人物从哪来、每个事件的起因在哪一镜"（storyboard-keyframes §2c，G32）。
   - **视线对准说话对象**：对话镜里说话人看着对手，正反打的视线方向与对手在画面上的位置一致、不看镜头；说话镜写 `gaze`，例外写 `gaze_reason`；起始帧和视频提示词都写视线方向（storyboard-keyframes §4，G43）。
   - **系统面板有科技感**：面板走 cut.py 的 `panel` 叠加，默认毛玻璃深色底、细描边外发光、标题栏图标、逐字打出、入场动画和入场音效；主题按画风在 `overlays.panel` 选 `tech` / `xianxia` / `scroll`（styles.md §12、edit-and-delivery §4）。
7. **写作与审查分离**：写的子代理不审自己写的；reviewer 子代理只出结论和修订要求。代理继承当前会话模型与配置，不写死供应商模型名；环境不支持代理时分轮审查，并明确说明没有独立审查者。
8. 不删产物：重拍开新 take；参考图重出改名归档。
9. **剧组分工**：同时开多个子代理按岗位分工——导演 `director`、角色设计 `character-designer`、美术/场景 `art-director`、场记/连续性 `script-supervisor`、剪辑/审片 `editor`，写作阶段另有编剧与 reviewer（按 7 分离）。岗位按当前运行环境的代理机制定义；只有平台明确支持项目代理文件时才写该平台目录，路径使用仓库相对路径。子代理只写本岗负责的文件和审查意见，**不提交生成任务、不做 git**；生成（串行）、mark、cut 由主会话统一做；Git 操作遵循项目已确认的交付策略。
10. **交付节奏**：同时做几部剧时，先把每部剧的 EP001 都出成片，再做各剧的后续集。项目是 git 仓库时先只读检查分支、工作区和远端；仅在用户已授权同步、且目标分支明确时执行 pull/commit/push，不默认推送主分支。回复里给出成片路径；不在只存在于临时目录（scratchpad）里的文件上积累进度——mark 清单、审查意见一律写进项目 `审查/`。
11. **生产纸面纪律**：H3 模型与尺寸只读取本项目已确认的 `profiles`，不得沿用技能历史档位；**每一张起始帧都要用当前环境的看图工具看过、通过目检才提交视频**；H3 不生成画外人声，要有画外声就拍说话人的在镜单人镜，或另生成音源镜用 `audio_from` 垫音；改剧本/分镜后只重拍受影响的镜头，重拍后重新 mark、重剪该集。
11b. **实拍错误表必读**：生产（F–J）开工前读 [production-and-review.md](references/production-and-review.md) 的「实拍踩过的错」E1–E12（改提示词后已排队的图不会更新、设定改了要 grep 旧词、过肩双人会画两次主角、三人同框第三人会跑到前景、状态细节要在两段提示词各写一句、audio_from 默认 phone、静音段 ASR 幻听、队列跑完要自动接手、断网要对账不重投……）。新发现的错误照同样格式追加进这张表：错在哪、以后怎么做。用 fal 通道见 [providers.md](references/providers.md) §7b。
12. **新角色与真人素材**：用户给新角色素材（照片、文档，可能放在 iCloud Drive `~/Library/Mobile Documents/com~apple~CloudDocs/` 或指定文件夹）时，按 [visual-assets.md](references/visual-assets.md) §11 接入：角色设计岗逐张看素材定名字、外形、服装锁、音色；导演岗定出场位置；编剧与 reviewer 分开改剧本；门全过（含 G28）。真人素材的角色形象保持正面尊重，不写殴打受伤、恶意羞辱，去掉能认出真实学校、姓名的标识。

## 项目与契约

目录布局、ID、`shots.json` / `refs.json` / `review.json` / `drama.json` 字段、机械门 G00–G45、自动决策默认表、续跑与收回：[pipeline-contract.md](references/pipeline-contract.md)。开工先读它，全程按它对账。各阶段审查问题、分级与输出格式统一在 [review-checklists.md](references/review-checklists.md)；多剧总览、导出资料、决策记录与规则冲突优先级见 [project-hub.md](references/project-hub.md)。

## 阶段与门

写作阶段（A0–E）可多集并行；生产阶段（F–J，含 G2 静帧预演）全项目串行。每阶段：读对应参考 → 产出 → 跑门 → 修到 0 error → reviewer 子代理（C、E 两阶段）→ 下一阶段。

| 阶段 | 做什么 | 读 | 产出 | 门 / 命令 |
|---|---|---|---|---|
| A0 原著拆解（仅改编项目） | 用户给的是小说、网文或多集原稿时：材料前提与入口判断、章节/分集精确索引、逐章功能提取、剧情单元聚合、人物归并、改编价值判定与分集候选，再立改编契约（删线、合并、换载体） | [adaptation.md](references/adaptation.md)；长篇另读 [series-long-form.md](references/series-long-form.md) | `项目开发/原著分析/`、`项目开发/改编契约.md`（模板 `assets/templates/改编契约.md`） | `novel_index.py index/verify/coverage`、`episode_intake.py index/verify/slice`；reviewer 按 review-checklists §R |
| A 立项 | 先查市场爆款题材库定首发平台与形态，再出 ≥6 个机制不同的候选（每个标注对标爆款与长青度）、按爽感检查表打分选一（饱和设定可以用，但必须写清新在哪里）；再四问定爽点、选一个主类型、人物与反派手段、装置条款、分集走向；写一行可生成性预算（台词角色、主场景、接触镜数）；选画风 `style_preset` 并全剧锁定，按画风选视频头句；定 `ai_label` | [market-hits.md](references/market-hits.md)；[premise-novelty.md](references/premise-novelty.md)；[story-engine.md](references/story-engine.md) §0–4、§10；[genre-cards/索引.md](references/genre-cards/索引.md)（选定主类型后读对应题材卡）；[styles.md](references/styles.md) §1；超过一季、集数多或续季读 [series-long-form.md](references/series-long-form.md) | `项目开发/系列简报.md`（含 `## 立项候选`、`## 爽感打分`）、`drama.json`（含 `style_preset`、`style`、`video_prompt_head`、`ai_label`） | 模板方括号清零；候选 ≥6 且打分表在（`next` 缺了会 warn）；`project_tool.py next` 不再指 A；G33、G36（视频头句）、G39；reviewer 按 review-checklists §A |
| B 情绪集纲 | 每集一行：受什么气、底牌与谁先知道、主角行动、反派失去、兑现、新问题、交接事实 | story-engine §5–6、§8；长篇的分集卡与跨集记忆见 series-long-form §4–5、§8 | `项目开发/情绪集纲.md`（长篇另有 `项目开发/跨集记忆.md`，模板 `assets/templates/跨集记忆.md`） | 每格具体；反派失去非空；reviewer 按 review-checklists §B |
| C 剧本 | 集纲那一行扩成可拍剧本；台词多、反应快、按用途写，单句短（拆句是为了句数多）；台词用目标语言母语口语直接写（一人称、称谓、敬语、语气词），专名标读音；每句台词带情绪标签；每个事件先写起因拍、关键物品先写来源拍；按单集秒表放落点，集尾与下集开头成对写 | [screenplay.md](references/screenplay.md)（§1 格式、§1b 现成剧本规范化、§2 秒表、§4 短、§4b 情绪、§4c 本地化、§5b 因果与事件起因、§8b 集间接缝、§9 分遍修订） | `EPxxx/剧本.md`（骨架 `assets/templates/剧本.md`） | `screenplay_lint.py <项目> <EP>`（格式）；`shots_tool.py check`（G16、G37 剧本部分先跑：新建空 shots.json 也能报剧本门）；reviewer 子代理按 [review-checklists.md](references/review-checklists.md) §A–C 审（含母语审读、事件起因、关键物品三问），两轮内清 Major |
| D 视觉设定 | 人物/地点/道具条目、锚点、音色、锁、身高与尺度锚点（厘米身高 + 头身比）、每个主场景一行平面图与动线；有台词的主要人物加头肩身份图 `IMG-<NAME>-FACE`；refs.json 增量 | [visual-assets.md](references/visual-assets.md)（§4b 空间逻辑、§12 尺度）、[image-prompts.md](references/image-prompts.md)（refs.json 的 `prompt` 怎么写）、[styles.md](references/styles.md) | `EPxxx/视觉设定.md`（骨架 `assets/templates/视觉设定.md`）、`参考图/refs.json` | `shots_tool.py check-refs`（G18–G20、G34；头肩图免全身/身高 warn）；`visual_lint.py`（V01–V06）；reviewer 按 review-checklists §D |
| E 分镜与提示词 | 每镜职责、起点与终点、必要身份/空间锚点、台词与表演；同一个人的连续戏合并成长镜头（拆就写 `split_reason`）；说话镜写 `gaze`（看对手、方向与对手位置一致）；事件镜 `requires_setup` 指起因镜、关键物品有来源镜或插入特写；插入/冲击镜过短写 `fast_cut_reason`；台词 `lang`、`reading`；参考图按功能分工；动作计划用 `planned_action_window`，跨正反打事实可用 `scene_state` | [storyboard-keyframes.md](references/storyboard-keyframes.md)（§2c 一眼看懂、§4 视线、§7b 长镜头、§7c 节奏下限）、[video-prompts-general.md](references/video-prompts-general.md)（§3b 长镜头写法）、[video-prompts-h3.md](references/video-prompts-h3.md)（用户指定 Seedance 时改读 [video-prompts-seedance.md](references/video-prompts-seedance.md)） | shots.json 与渲染分镜 | 机械门无 error（G42–G45 是 warn，逐条判断）；warn 结合叙事判断，不能靠堆提示词消警告；`visual_lint.py`；reviewer 按 review-checklists §E |
| F 参考图 | 身份图、底板、道具图 | visual-assets §7–8、§4b、§12、image-prompts §3–4、§9、[production-and-review.md](references/production-and-review.md) §4；走官方接口时读 [providers.md](references/providers.md) | `参考图/IMG-*.png` | `produce.py refs`；模型 查看每张 PNG 目检（底板必答"空间说不说得通"、尺寸是否现实），不过 `--retake` |
| G 起始帧 | 每镜起始帧 | production-and-review §3–4 | `起始帧/F_*_t*.png` | 先金丝雀一镜；`produce.py frames`；逐张目检（一人、朝向、持物、留空、无字、像参考，加 production-and-review §4b 细节与比例清单 9 项）；`review_tool.py mark --frame-take` |
| G2 静帧预演 | 起始帧全部通过后、提交视频前（金丝雀一镜除外），按镜序把起始帧拼成预演片，只看画面复述情节 | production-and-review §3b | `审查/<EP>-预演.mp4`、`<EP>-预演.jpg`、`<EP>-预演.md` | `review_tool.py animatic`；查看接触表逐条答五问；有"看不到"的情节点回 E 或 G；`<EP>-预演.md` 首行写「结论：PASS」才进 H（`next`、`produce.py all` 都查这一行，写「结论：REVISE」或文件不在都不放行） |
| H 视频 | 在授权批次内生成；ASR 标出差异，先听审再决定是否重拍；另配音的，语言参数 = 台词语言、参考音频是同语言母语者，听感五问含口音与句尾语调 | [production-and-review.md](references/production-and-review.md)（§10 配音）；官方视频/语音/配乐接口读 [providers.md](references/providers.md)（`providers.py`） | 视频与候选检查 | `produce.py videos --asr` 不凭分数自动重拍；ASR 读错专名或识别成别的语言（"语种疑似不符"）即不合格 |
| I 审片 | 对具体 take 看画面、听声音、核连续性；测动作和对白区间，记录证据 | [quality-contract.md](references/quality-contract.md)、review-checklists §F–J | review.json 每 take 的 assessment/edit/verdict | 未审、失败或过期记录不能进正式剪辑；草剪显式用 `--draft` |
| J 剪辑 | 取用（出点包住动作、不低于节奏下限）、字幕（行长、阅读速度）、叠加（系统面板按 `overlays.panel` 主题出科技感样式）、声音设计（底噪、音效、白光、配乐另做）、响度与真峰、AI 生成标识、成片 | [edit-and-delivery.md](references/edit-and-delivery.md)；多剧总览与导出读 [project-hub.md](references/project-hub.md) | `成片/EPxxx.mp4`、`剪辑单.md` | `hub_tool.py measure`（交付数字）、`hub_tool.py grade`（接镜调色，可选）；`cut.py`（`ai_label` 自动叠在前 3 秒；剪辑单标过短镜和同场平均镜长；`cut.py --panel-demo` 预览面板）；成片再跑一遍 ASR 对全集台词；交付核对五步（edit-and-delivery §7，含"关键物品从哪来、事件起因在第几秒"） |

## 每次执行

1. `project_tool.py status` 看全貌，`next` 定位阶段；读 `项目开发/决策记录.md` 和上一集的 `[连续性]`（三回锚：本批任务、上一批结束状态、当前规则）。
2. 做当前阶段，跑门，修 error；warn 逐条判断后豁免或修。
3. C、E 阶段派 **reviewer 子代理**（没参与写作、继承当前会话模型）：按 [review-checklists.md](references/review-checklists.md) 引用证据写 `审查/<EP>-审查.md`（骨架 `assets/templates/审查.md`；分级、结论 PASS/REVISE/BLOCKED 的判定与输出格式见其 §0），每条问题带位置、证据、影响、最小修复，末尾 `keep:` 清单；写完跑 `review_md_check.py 审查/<EP>-审查.md`。writer 改完对 keep 清单做字面比对。同一 Major 两轮没过：按 reviewer 的修订建议直接改并记未决，不停。
4. 生产阶段用少量样片覆盖身份、接触、长对白等实际风险；先静帧预演再批量视频。重拍先诊断、受授权预算限制；take 用尽仍缺关键情节时暂停正式成片并改分镜，不能自动 weak 放行。
5. 每集出成片后：每秒抽一帧拼网格用看图工具目检（镜序、人物、叠字位置、前 3 秒 AI 标识），整片跑一遍 ASR 核对全集台词（edit-and-delivery §7）；`project_tool.py status`，把决策、未决、weak 镜写进决策记录；按已授权的 Git 交付策略同步，汇报成片路径；授权范围内继续下一集。
6. 全部集完成后汇报：每集时长、镜数、重拍次数、weak/drop 镜、未决项、决策记录摘要。

## 自动决策（不问人）

创作配置默认 general，不替用户选择复仇或异能。commercial_fast 才启用密对白与快反应参考；规模和时长作为可修改计划，模型与尺寸须明确。ASR 不设自动放行线；take 用尽需判断缺陷是否影响核心故事。

## 修改纪律

- 改一拍，连读三拍：改过的镜头前后各一镜一起重读边界链（G26）。
- 修门只改诊断出的那一项；不往提示词里堆负面词。
- 台词只能在剧本阶段改；分镜和提示词阶段发现台词装不下，先加秒数（同一个人就写成一个长镜头，上限 `shot_seconds.max`），仍装不下再回剧本合并同质节拍；换人说话才拆镜。
- 语速：`drama.json` 的 `speech_rates` 是估算值，第一集 ASR 出来后用实测（词级时间）校准，写回配置。
- 模型行为先记账再立规矩：实测到的模型行为（某个写法让口型、动作、画风变好或变坏）先写 `项目开发/模型观察.md`，写清 N 次里几次、能判断什么、混杂因素；同一写法有效 ≥ 3 次才升级成 references 里的规则，单次改善只记录。[社区][推断]

## 续跑与中止

已有产物通常跳过；中断后先查任务账本。存在提交结果未知的记录时，先按[运行边界与恢复](references/runtime-boundaries.md)对账；禁止直接重投。`STOP` 文件当前任务做完后停；`DEADLINE=YYYYmmddHHMM` 到点不再提交。任务号在 `脚本/ids.log` / `jobs.jsonl`，被杀后 `h3_client.py collect` 收回。

## 按需深读的参考

本技能只读写 `drama.json` 项目与结构化镜头/素材账本。遇到旧的 `short-drama.json` 五文档项目不自动迁移：用户明确要转时另建 `drama.json` 项目，剧本按 [adaptation.md](references/adaptation.md) §5 当多集原稿接入、按 [screenplay.md](references/screenplay.md) §1b 规范化，原项目保留不动。

阶段表只列每阶段必读的节；某个问题要更完整的方法时再读下面对应文件（不必全部加载）：

| 问题 | 读 |
|---|---|
| 爽点、冲突引擎、装置条款、机制循环、揭示与反转、单集契约 | [story-engine.md](references/story-engine.md) |
| 点子新不新、候选怎么出和打分；市场对标 | [premise-novelty.md](references/premise-novelty.md)、[market-hits.md](references/market-hits.md) |
| 某个题材怎么写、开场入口、钩子、制作难点 | [genre-cards/索引.md](references/genre-cards/索引.md) 与各题材卡 |
| 长篇连载、续季、人物弧线、跨集记忆 | [series-long-form.md](references/series-long-form.md) |
| 小说/网文/多集原稿改编、对标作品只学机制 | [adaptation.md](references/adaptation.md) |
| 剧本格式、场景发动机、对白手艺、分遍修订、续写 | [screenplay.md](references/screenplay.md) |
| 资产拆解、身份与变体、声音方向、连续性变化记录 | [visual-assets.md](references/visual-assets.md)、[scene-state-and-reveal.md](references/scene-state-and-reveal.md) |
| 参考图提示词（身份图、转面板、底板、道具、局部编辑） | [image-prompts.md](references/image-prompts.md) |
| 调度、轴线、冻结关键帧、长镜头与节奏 | [storyboard-keyframes.md](references/storyboard-keyframes.md) |
| 视频提示词：通则 / H3 / Seedance | [video-prompts-general.md](references/video-prompts-general.md)、[video-prompts-h3.md](references/video-prompts-h3.md)、[video-prompts-seedance.md](references/video-prompts-seedance.md) |
| 官方接口通道、配音、配乐、失败分类与收回 | [providers.md](references/providers.md)、[runtime-boundaries.md](references/runtime-boundaries.md) |
| 审片、重拍决策、质量证据 | [production-and-review.md](references/production-and-review.md)、[quality-contract.md](references/quality-contract.md) |
| 剪辑、字幕、声音、调色、交付核对 | [edit-and-delivery.md](references/edit-and-delivery.md) |
| 各阶段审查问题、分级、结论与格式 | [review-checklists.md](references/review-checklists.md) |
| 多剧总览、导出、决策记录、规则冲突优先级 | [project-hub.md](references/project-hub.md) |
| 画风与系统面板主题 | [styles.md](references/styles.md) |

外部来源见 README 的来源表；原 short-drama 十一件套的内容已并入上面各文件，逐文件去向记在 `references/_merge-ledger/`（历史台账，不是运行时参考）。

## 安装维护

`python3 scripts/selftest.py`：起假中转把整条链离线跑一遍（含提交恢复回归、G36–G45、静帧预演、父帧、AI 标识、面板渲染与入场动画、剪辑单节奏统计）。需要 ffmpeg/ffprobe、Pillow、requests；只有显式设置 `SELFTEST_ASR=1` 才测 ASR，模型需已缓存在本地。只测提交与恢复可运行 `python3 scripts/client_selftest.py`，不需要 ffmpeg/Pillow。

无 ffmpeg/ffprobe 时可运行 `python3 scripts/selftest.py --no-media`，覆盖初始化、机械门、渲染、假中转生产与续跑；不验证真实视频解码、预演、ASR 或剪辑。

`python3 scripts/merged_selftest.py`：合并进来的新工具离线自测（`hub_tool`、`providers`、`visual_lint`、`screenplay_lint`、`review_md_check`、`novel_index`、`episode_intake`），不起中转、不调用付费接口，有 ffmpeg 时顺带实测 `hub_tool measure/grade`；只跑其中一项用 `python3 scripts/merged_selftest.py <名字>`（或 `-k <名字>`）。`python3 scripts/quality_selftest.py` 测语义筛查、take 审片记录、剪辑准入与场景状态。
