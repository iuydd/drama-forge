---
name: drama-forge
description: DramaForge：开发、改编、制作、审查与续做 AI 短剧或漫剧，包括剧本、分镜、生成、剪辑和 drama.json 项目续跑。在授权预算内自动推进制作，分别报告制作验收、声音验证和观众反馈；不承诺无人验收的商业效果。
license: MIT
---

# 爆剧引擎 / DramaForge

把一个点子做成能追看的商业爽剧成片，在用户已授权的范围和成本边界内连续执行。商业爽剧的密集对白、即时反应和顺叙是本流程的创作预设，当前请求和项目设定优先；但项目设定不能放宽下面的「防钻空子总则」和质量底线。

## Quick Start

```bash
S="/实际安装目录/drama-forge/scripts"  # 替换为本 SKILL.md 所在目录下的 scripts
python3 "$S/selftest.py"                                                  # 安装后跑一次，离线
python3 "$S/project_tool.py" init <项目目录> --title "剧名" --episodes 6 --dialogue-lang ja --genre 智斗复仇
python3 "$S/project_tool.py" next <项目目录>                               # 任何时候：下一步该做什么
```

生产需要环境变量 `H3_API`（你的 H3 中转地址，也可写在 `drama.json` 的 `api_base`）和 `H3_STUDIO_TOKEN`（只从环境读，不落盘）；审片需要 `ASR_PY`（装了 faster-whisper 的 python，例如 `~/.venvs/asr/bin/python`；不设则自动扫 `~/.venvs/*`）。

## 防钻空子总则（所有条文按这里的读法执行）

本技能假设执行者会被诱惑着抄近路：用最少的工作宣称完成、只守字面、挑宽松的那条规则。下面几条堵的就是这些路，任何其他条文、参考文件、模板、项目设定都不能放宽它们。

1. **按目的与适用范围读规则**：先按 project-hub §6 判断优先级；授权、质量底线和 error 门不得由代理放宽。同层创作默认有冲突时，选择满足叙事目的且已验证成本更低的办法，记明本镜证据和影响范围，不因“更严”就扩大到全剧。授权或事实仍有歧义时只暂停依赖部分，不利用空隙绕过验收。
2. **授权只来自用户原话**：用户授权 = 用户在对话里说的话，记在 `项目开发/决策记录.md`，`拍板人: 用户`、`用户原话`、日期三项齐全才算。`拍板人: 代理` 的行、模板、示例、历史项目、本技能里的案例都不构成授权；"继续""全自动""你看着办"只授权按既定规则往下做，不授权放宽任何规则、换模型或加预算。
3. **质量底线不可被项目设定覆盖**：画面不出字（4）、台词逐字（5）、必拍事实（6g）、对话对象与空间关系可辨（11c）、槽位并发与提交上限（2）、模型由用户指定（1b）、写审分离（7）、不删产物（8）。只有用户原话点名某一条、说明本项目放宽，才放宽那一条。
4. **"看过/听过/审过"要留证据**：每次目检写可抽查的具体观察（几个人、各在哪朝哪、脚下是什么、每只手属于谁、道具几件、和上一镜接不接得上），绑定被审文件的 sha256；"看过无问题""9/9 过""自然"这类套话按没做算。文件变了（重拍、重出、重剪），旧结论自动作废。网格和缩略图只用来找可疑处，放行要看过单张原图。
5. **模型听不到声音**：`listen_ok`、口音、语调、情绪听感只能由真人（用户或用户指定的母语者）签，记下 `listener`；执行代理和任何子代理一律写 null、汇报写"未听审"。不许用"听感"推翻 ASR，也不许从 ASR 文本推断听感。
6. **放行不自签**：预演、C/E 审查、成片终验的 PASS 要逐条答案填满、输入指纹没变；C/E 审查由没参与写作的 reviewer 写，主会话不得改 reviewer 原稿（修订另写一份）。
7. **逃生口有边界**：
   - `weak` 不能用在承担必拍事实或关键情节的镜头上，这类镜头只有 retake、改分镜、回剧本三条路。
   - 「未决」不能用在 Blocker 和剧情事实类 Major 上；其余未决写轮次和决策记录编号，结论写 `PASS（未决 N）`。
   - 「用户确认」必须是用户看过问题清单之后的原话、点到问题编号；拿不到就写"待确认"，该集汇报为**未交付**。剧情事实类缺陷不能靠用户确认放行。
   - `waive` 只能豁免 warn 门，带门号、理由、决策记录编号；error 门永不豁免。
   - 各种例外理由（`split_reason`、`gaze_reason`、`fast_cut_reason`、单人镜理由等）要过**搬家测试**：理由原样挪到另一镜仍然成立，就是套话，按没写算。"适当""自然""合理""若干"这类词不能单独充当规格。
8. **影响范围按依赖算**：重拍或重出一镜，作废的不只是这一镜，还有链式出帧的全部下游镜（起始帧取自本镜末帧的）、相邻镜的连续性结论、该集预演和成片终验。
9. **不动门**：运行中不改本技能的脚本、门逻辑、阈值、白名单，不改 `drama.json` 里的门阈值或固定句来让门通过。门误报就记进决策记录、告诉用户，按更严的执行。
10. **如实汇报**：没做的写没做，没验证的写未验证；镜数、重拍数、weak/drop、花费取自脚本输出，不手写估计。
11. **生成模型也会钻空子**：提示词里没写死的，图像/视频/TTS 模型都会按最坏情况补（多一个人、少一个人、朝向乱、手凭空出现、停顿处补字、镜内硬切、出字）。提示词按「封闭世界」写，见 [video-prompts-general.md](references/video-prompts-general.md) §2b。

## 硬约束（一直有效）

1. **有界自动执行**：按[运行边界与恢复](references/runtime-boundaries.md)先明确本轮集数、任务范围、模型/尺寸、提交次数上限及成本边界；已有明确授权（按总则 2 的用户原话）直接沿用，范围内连续执行。缺模型配置、触及预算、STOP/DEADLINE、提交结果未知或真实创作分叉时停止依赖工作。常规创作决定写进 `项目开发/决策记录.md`。
1a. **全自动 = 不能弹权限请求**（用户 2026-09-26 定）：主会话和子代理的命令都不能触发权限确认弹窗。禁止 `rm`/`rm -f` 配变量路径或通配符（每次输出到新目录，或字面路径 + `/usr/bin/trash`）、禁止前台 `sleep` 后接命令（用后台任务或 until 循环）、禁止 curl/wget 直连（用 python requests）；遇到会弹窗的写法就换写法。
1b. **模型由用户指定**：生成用的模型、档位、分辨率（视频、图片、TTS、对口型）由用户指定；项目里用户已定的默认（`drama.json` / `项目开发/决策记录.md`）可直接用；用户没指定的，不许自选、不许擅自换，列 2–3 个候选和价格交用户定。新项目 `profiles` 初始为空；`profiles` 每一项都要能指回决策记录里 `拍板人: 用户` 的那一行（`profiles_source`），指不回的按未授权处理；模板、技能中的案例和历史项目决定都不构成当前项目授权；镜头级、参考图级另写档位也要有同样的出处（`produce.py` 提交前拒绝与 `profiles` 不同的镜头级/参考图级档位；`profiles_source` 缺失只报 warn，它指向的是不是用户原话那一行脚本不查，靠规则）。
2. **按槽位提交**：h3studio 同时在飞的任务不超过 `/api/status` 的 `capacity.slots_total`（2026-09-26 为 9 台各 1 个，用户定：可以并发 9 个），有空槽才提交；`produce.py` 走 h3studio 时默认就按槽位数并发，`--jobs` 只能调小。POST 永不自动重发；先查账本收回未收回的任务。fal、kling 等云端通道默认逐镜，`--jobs N` 并行要用户原话单独授权并发（规则要求，脚本不查授权）。
3. **镜头服务可读性**：对话镜按 11c 建立明确的说话对象与空间关系，默认让听者入画；接触用双人镜、可辨手部特写或有意省略，确保前后归属和因果成立。多人镜把人数写死（`exactly N`）。景别、节拍和长度由叙事及项目模型能力决定，不固定脸部比例或每镜秒数。详见 storyboard-keyframes.md。
4. **生成画面不出字**：字幕、面板、印章字全部后期叠加；手机屏幕背对镜头。
5. **台词逐字等于剧本**（G09/G10）；能力规则/装置条款先改系列简报再进剧本。
6. **剧情优先**：审片只看剧情、动作可读、台词完整、有无出字、有没有认错人；画质不作重拍理由。"画质"只指清晰度、噪点、质感；多人少人、多手少手、手形错、出字、认错人、镜像、镜内硬切、人站错一侧都是内容缺陷，不能归为画质放过。但**关键情节点的动作没生成出来、方向反了、或被剪在出点之外，是必须处理的问题**（重拍、改取用区间或改分镜），不能用"不重拍"放过；审片必须看接触表，逐镜写出职责动作在原片第几秒发生（production-and-review §5）。
6a. **点子要新、要爽**：立项先出 ≥6 个机制不同的候选、按爽感检查表打分选一；看破谎言、摸物知价、挨打到账、强制说真话、短时回溯、读心、系统面板、重生复仇、赘婿战神退婚、亮令牌等饱和设定可以用，但必须带新内容（新规则/限制、新使用场景、新视角、新兑现方式、新反制循环、新组合或新世界观/职业承载，至少一项），在候选表写清新在哪里，只换皮不算（[premise-novelty.md](references/premise-novelty.md)）。出候选前先查[市场爆款题材库](references/market-hits.md)，定首发平台与形态，每个候选标注对标的爆款组合与长青度（长青的是能持续升级的金手指，隐藏大佬亮身份型多是昙花一现）。
6a1. **金手指不要代价，最多要限制**（用户 2026-09-26 定："有代价就不爽了"）：主角的能力、系统、外挂不设使用代价（掉寿命、忘记人、受伤、失去关系等），只设限制（次数、范围、冷却、触发条件）。压力来自对手和规则，不来自能力反噬主角。references 里写"代价"的地方，凡指主角金手指的，一律按"限制"理解；对手和反派付代价不受影响。
6b. **开场服从故事**：默认 `opening_mode: story_driven`，先建立可理解的冲突；只有已选异能获得型故事才用 `power_acquisition` 开场。**闪回、闪前、插叙只在观众看得懂时用**（用户 2026-09-26 定）：观众要能一眼分清这是过去还是将来（字幕时间卡、台词或画面标记），而且不会把因果读反——EP001 片头闪前没有任何标记，观众先看到亮「嘘」、后看到撞头，就以为能力早就有了，这种不许。`cut_order` 调序的地方写 `flash_reason`（看懂靠什么标记）；预演和 reviewer 必答「只看画面和字幕，观众能否分清时间、因果有没有读反」，答不上就按时间顺序剪。
6c. **信息可读且不提前泄底**：交代当前理解行动所需的场景与规则；规则可以通过行动、对白或字幕呈现。区分世界事实、角色所知、观众所知；有意隐藏的信息记揭示计划，不强制事先展示全部道具。
6d. **场景连续**（否则一切镜头观众就以为换了地方）：同一场戏所有镜头的背景必须读得出是同一个地方。同场的反打底板必须以主底板为参考图派生（refs.json `refs`，G28），目检底板成对看；起始帧目检把本镜和同场上一镜并排比背景；有底板的镜头禁止水平镜像起始帧。**让出图模型转机位要有条件**（2026-09-27 用户实拍：给餐厅底板让它换角度，出来是另一个房间；用户定：提示词严谨到能保证场景一样时可以转）：默认每个机位先有一块自己的底板（反打、侧面从主底板派生并目检"空间说得通"），起始帧挂同机位底板、提示词写"保持 Picture 1 的背景与机位，只加人物/改人物"。要在出帧或派生时直接换角度，三条都满足才可以：①用能按参考图编辑的档位；②提示词把场景写成封闭清单——Picture 1 里的固定物件（门、窗、柜、楼梯、灯、画、桌椅）逐一点名，写明新机位朝哪面墙、每件物件在新画面的哪一侧哪一段、哪些在新机位下看不到，并写"no other furniture, doors or windows"；③出图后与主底板并排目检，逐件核对位置与材质，写进证据。任一条不满足或目检发现多出/缺少/挪位的固定物件，就退回先派生底板。带底板或父帧的起始帧、派生参考图必须用能按参考图编辑的档位（如 qwen21）；只把参考图当风格用的档位（h3studio krea2 系列，`drama.json` 的 `style_only_profiles` 可覆盖）只出无参考的身份图和道具图，`produce.py` 提交前拒绝违例。
6e. **画面真实、因果可见、声音有情绪**（六条一起守，出处在括号里）：
   - **风格锁定**：立项在 `drama.json` 选 `style_preset`（真人都市、古装、修仙、日漫、国漫 3D、韩漫、写实 CG 七选一），全剧一句 `style`，不在单集单镜换画风（[styles.md](references/styles.md)，G33）。
   - **比例与细节**：按项目画风和世界设定核对尺度、手形、持物、光源和透视；提示词仅补影响本镜的必要锚点（storyboard-keyframes §6b）。
   - **场景合理**：门后不接门、下楼楼梯不接上楼楼梯、窗外景与楼层一致、走廊通向合理；每个主场景写一行平面图与动线，同场各底板拼得回这张平面图，底板目检必答"空间说不说得通"（visual-assets §4b）。
   - **因果与信息权限**：世界内原因要成立，观众获知顺序按悬念设计；`requires_setup` 仅记录必须预先披露的依赖。跨镜状态与隐藏信息见 [scene-state-and-reveal.md](references/scene-state-and-reveal.md)。
   - **环境动态**：仅在自然存在或承担情节时描述；静止背景本身不构成失败。明确需要运动时填 `environment_motion_required` 与 `environment_motion`（G35）。
   - **台词有情感**：每句台词写 `emotion`（情绪·强度·语速·音量）；配音按情绪选参考音频或用支持 instruct 的 TTS；配音验收在 ASR 之外加听感（情绪对不对、喊叫句有没有力度）（screenplay §4b、production-and-review §10，G31）。
6f. **听得像母语、看得懂、节奏稳**（用户看完 EP001 的反馈："说话语调，口音很奇怪，台词也不本地""镜头切换太快""要完整交代事情，关键物品的来源""系统弹窗做的有科技感一点""人物要看着他说话""事件一定要交代起因""同一个人就不要弄两个镜头"）：
   - **说话像真人**（用户 2026-09-26 定）：用词符合这个人的身份和此刻的场景（饭局上、吵架时、病床前说的话不一样），情绪和强度符合场景（安静场合不喊、生死关头不平淡），口音是目标语言母语者的自然口音，不像播音、不像朗读。剧本台词、视频提示词里的语气描述、配音参数三处都按这条写。
   - **台词本地化与母语口音**：台词是目标语言母语者日常会说的口语（一人称、称谓、敬语层级、语气词、年龄身份口吻），禁止翻译腔和书面腔；reviewer 做母语审读，逐句标不自然处并给改写。配音的语言参数显式等于台词语言，克隆参考音频是同语言母语者的对话录音，专名写 `reading` 并在配音前校对；ASR 读错专名或识别成别的语言即不合格（screenplay §4c、production-and-review §10，G44）。
   - **长镜头与节奏下限**：同一场里相邻两镜主体是同一个人、中间没有别人或插入镜，默认合并成一个长镜头（按内容 8–10 秒常见，上限 `shot_seconds.max`，H3 15 秒），只有景别/机位/剧情明显变化或时间跳跃才拆并写 `split_reason`（G45）。成片对白镜不短于台词说完 + 0.8 秒且 ≥ 2.5 秒、反应镜 ≥ 1.5 秒、插入/冲击镜更短要写 `fast_cut_reason`、同场平均镜长 ≥ 2.5 秒；一句台词在一个镜头里说完（storyboard-keyframes §7b–7c、edit-and-delivery §2，G42）。
   - **一眼看懂**：每个事件（登场、摔落、冲突爆发、受伤、闯入）之前一定有起因（画面、台词或声音），事件镜用 `requires_setup` 指向起因镜；关键物品第一次出现要有来源镜，或清楚的插入特写 + 台词点明；关键事件的起因、经过、结果三拍都要有画面或台词；reviewer 和静帧预演必答"只看画面加字幕，每个关键物品/人物从哪来、每个事件的起因在哪一镜"（storyboard-keyframes §2c，G32）。
   - **视线对准说话对象**：对话镜里说话人看着对手，正反打的视线方向与对手在画面上的位置一致、不看镜头；说话镜写 `gaze`，例外写 `gaze_reason`；起始帧和视频提示词都写视线方向（storyboard-keyframes §4，G43）。
   - **系统面板有科技感**：面板走 cut.py 的 `panel` 叠加，默认毛玻璃深色底、细描边外发光、标题栏图标、逐字打出、入场动画和入场音效；主题按画风在 `overlays.panel` 选 `tech` / `xianxia` / `scroll`（styles.md §12、edit-and-delivery §4）。
6g. **必拍事实不可妥协、成片终验、声音如实**（2026-09-26 外部深度审查：数量错的道具、没拍出的认输动作被"台词能解释"放行；成片金额断行遮脸、入点切进语气词；"audio pass"其实只是 ASR 通过）：
   - **必拍事实**：每场 3–5 条只看画面也必须读到的事实（数量、谁做了什么、状态、反派具体损失、身份），剧本 `[连续性]` 写「必拍：」，分镜落成 `scenes[].must_show` 与镜头 `must_show_ids`（G46–G47）；任何阶段没成立只能重拍、改分镜或回剧本改，"台词能解释""观众数不出来"不是放行理由，缺的关键动作不能靠延长镜头、补旁白或字幕替代；删镜、改剪点前对照 must_show 与 requires_setup 确认因果证据还在（storyboard-keyframes §2e、production-and-review §5c、edit-and-delivery §2d）。
   - **演出承接、能力只讲一次**：对白镜的 motion 先写人物怎样接住对方的行为、做了什么改变局面，不是轮流说明情况（G49）；能力规则讲清后只留一句提醒，新角色确认 ≤1 句，跨集回顾 ≤5 秒（G48，screenplay §5b3、storyboard-keyframes §8c）。
   - **预演是粗剪**：视频前的预演带临时对白（草音或字幕）、按计划取用时长、标动作起止和反应拍，预演片与结论留档（production-and-review §3b）。
   - **成片终验**：每集从最终 MP4 重新验收必拍事实、文字排版（金额数字专名不断行、叠字不压脸和眼、长文字分屏）、台词边界（入点不切进台词或语气词，字幕 = 成片可听内容）、切点、片尾无拖尾停帧：`final_qa.py` 写机读的 `审查/<EP>-final-qa.json` 与 `.md`，模型看图、听审后写结论 `审查/<EP>-成片终验.md`（edit-and-delivery §7b）。
   - **声音三项如实**：`asr_ok`（识别正确）、`listen_ok`（真人听过、听感自然，带 `listener`，见总则 5）、`sync_ok`（口型同步）分开记；没听、没核就是 null，显示为"未验证"，不得汇总成"通过"；`asr_ok` 只能来自对当前文件实际跑出的 ASR 结果；关键能力词、专名 ASR 有分歧交母语听审。
7. **写作与审查分离**：写的子代理不审自己写的；reviewer 子代理只出结论和修订要求。reviewer 的任务书只给文件路径和审查范围，不许写"只看格式""从宽""重点放过"之类的限定；reviewer 原稿不许改。各环节用哪个模型按 [model-routing.md](references/model-routing.md)（用户 2026-09-27 定：Claude 下写作 Opus、审查 Sonnet、补账与格式等轻活 Sonnet；Codex 下写作与审查 GPT-6 Sol、轻活与攻防第 1 轮 GPT-6 Luna）：写作类子代理（worker）不降级；审查类（reviewer）Sonnet 5 medium；补账、格式、机械门修复、逐章抽取这类不改剧情的轻活派 `light`；提示词攻击按 11d；看图目检留在主会话；环境不支持代理时分轮审查，并明确说明没有独立审查者。
8. 不删产物：重拍开新 take；参考图重出改名归档。
9. **剧组分工（2026-09-27 按需启动，减少交接与重复输入）**：岗位是职责，不是必须各开一个子代理。小批量任务默认由同一个执行者兼任；只有存在可独立完成、产物互不覆盖的工作批次时才拆开并行，任务书列明兼任职责及验收项，不能漏岗。C/E 的独立 reviewer 和 11d 的攻击模型、轮次保持不变，作者不能兼任 reviewer。可分工的岗位——导演 `director`、角色设计 `character-designer`、美术/场景 `art-director`、场记/连续性 `script-supervisor`、剪辑/审片 `editor`，写作阶段另有编剧与 reviewer（按 7 分离）。岗位按当前运行环境的代理机制定义；只有平台明确支持项目代理文件时才写该平台目录，路径使用仓库相对路径。子代理只写本岗负责的文件和审查意见，**不提交生成任务、不做 git**；生成（按槽位并发）、mark、cut 由主会话统一做；Git 操作遵循项目已确认的交付策略。
10. **交付节奏**：同时做几部剧时，先把每部剧的 EP001 都出成片，再做各剧的后续集。项目是 git 仓库时先只读检查分支、工作区和远端；仅在用户已授权同步、且目标分支明确时执行 pull/commit/push，不默认推送主分支。回复里给出成片路径；不在只存在于临时目录（scratchpad）里的文件上积累进度——mark 清单、审查意见一律写进项目 `审查/`。
11. **生产纸面纪律**：H3 模型与尺寸只读取本项目已确认的 `profiles`，不得沿用技能历史档位；**每一张起始帧都要用当前环境的看图工具单张看过原图、按总则 4 写下具体观察并 `mark --frame-take N --evidence "…"` 后才提交视频**；可以先用 `assets/templates/起始帧初筛.md` 交便宜模型初筛（Codex 下 GPT-6 Luna，见 model-routing.md），初筛只排看图顺序，不替代主会话逐张看原图；H3 不生成画外人声，要有画外声就拍说话人的在镜单人镜，或另生成音源镜用 `audio_from` 垫音；改剧本/分镜后重拍受影响的镜头（范围按总则 8 算，含链式出帧下游），重拍后重新 mark、重剪该集、重做预演与终验。
11b. **实拍错误表必读**：生产（F–J）开工前读 [production-and-review.md](references/production-and-review.md) 的「实拍踩过的错」E1–E12（改提示词后已排队的图不会更新、设定改了要 grep 旧词、过肩双人会画两次主角、三人同框第三人会跑到前景、状态细节要在两段提示词各写一句、audio_from 默认 phone、静音段 ASR 幻听、队列跑完要自动接手、断网要对账不重投……）。新发现的错误照同样格式追加进这张表：错在哪、以后怎么做。用 fal 通道见 [providers.md](references/providers.md) §7b。
11d. **提示词漏洞：机械检查 + 攻防（用户 2026-09-26 定，严格执行）**：每条视频提示词和起始帧提示词先过机械门 G54（逐条对应 [prompt-loopholes.md](references/prompt-loopholes.md) 的编号 L01–L30：左右口径、锁机位、位移距离、时间窗、物理速度落地、出画路径、陈设清点、前后位置、门窗开度、头部句运镜、必备句、集合式保持、锚点短语、分工句两半、光句、伪量词、审片证据等）。**写法总则：画面里看得见的一切，要么逐项写死，要么被排他句覆盖；生成模型、攻击子代理、审片模型都按「字面合规、交最差成品」的对手处理，验收只认留下证据的检查**（video-prompts-general §2b）。只有两类镜头再派攻击子代理：**高风险镜头**和**生成出来不好、要重拍的镜头**（重拍前先攻，找出失败的漏洞）。高风险镜头只按动作描述（motion）判定，用 `scripts/adversary_plan.py list <项目> <EP>` 列出，不凭感觉扩大：动作里有物理参与（摔、滑倒、撞、倒下、跌、打翻、扔、砸、泼、洒），或人与人的身体接触（握/抓/拽/拉/扶/按/盖/推/拍/搂/抱 接手腕、手背、手臂、肩、袖口、后背、腰、衣领、头发）；镜头写 `"adversary": true/false` 可强制纳入或排除（排除写 `adversary_reason`）。多人同框、承担必拍事实、新场景本身不触发——它们由 G52 与分镜审查覆盖（2026-09-27 用户定"优化"：按旧写法一集 28–57 镜全被攻，按新判定约 0–11 镜）。`adversary_plan.py tasks <项目> <EP> --model "<本项目视频模型与参数>"` 只为提示词有变化的高风险镜写 `-vN.txt` 和任务书，第 3 轮起不再生成；`adversary_plan.py status` 列出缺判断栏的清单。攻击子代理的任务是在不违反提示词任何一句的前提下做出最让导演失望的成品，只交最致命的 5 条和修补；任务书用 `assets/templates/攻击任务书.md`，只填模型与参数、这一镜的目的、起始帧/底图路径、提示词文件路径，不给剧本、分镜、规则、SKILL.md、别的轮次清单。**最多两轮**：第 1 轮 `isolated_agent.sh <项目> <任务书> adversary`（Sonnet 5，medium）；问题大且仅需局部、明确的修补时，修复后提交；问题不大（含未发现问题），或第一轮修复涉及动作路径、人物关系、镜头结构的大幅修改时，修复后必须再做第 2 轮 `adversary2`（Opus 5.5，low，全新子代理），修完提交。第一轮问题不大不代表安全，第二轮用于查找第一轮可能遗漏的隐蔽漏洞；大幅修复也可能引入新漏洞。第二轮只审修复后的当前版本，仍不提供第一轮清单。每轮提示词存 `审查/adversary/<ID>-vN.txt`、清单存 `-rN.md`（末尾写判断、修了哪几条，以及是否涉及上述大幅修改和第二轮是否触发；2026-09-27 补充：避免大幅修复后直接提交）；新漏洞追加进 prompt-loopholes.md，出现 ≥2 次且能写成规则的升级进 G54。其余镜头的 `adversarial_preflight`（G52）由主会话自己写 3 条。
11c. **对话对象可辨、连续性按实际依赖维护**：对白默认两人同框或听者背影在前景。已建立空间关系的单人对白可用，但 `single_reason` 必须引用建立镜、对象方位、视线与切回承接，以及本镜叙事用途；自言自语和对全场喊话也写具体理由。G53 仍检查理由，reviewer 与预演检验是否读成对空气说话，失败退回同框。起始帧默认用经核验的同机位底板、身份图或通过的 `frame_parent`；只有必须继承前镜动作终态时才用视频出点帧，不能为链式出帧绕过 G2。见 [storyboard-keyframes.md](references/storyboard-keyframes.md) §1、错误表 E33。
12. **新角色与真人素材**：用户给新角色素材（照片、文档，可能放在 iCloud Drive `~/Library/Mobile Documents/com~apple~CloudDocs/` 或指定文件夹）时，按 [visual-assets.md](references/visual-assets.md) §11 接入：角色设计岗逐张看素材定名字、外形、服装锁、音色；导演岗定出场位置；编剧与 reviewer 分开改剧本；门全过（含 G28）。真人素材的角色形象保持正面尊重，不写殴打受伤、恶意羞辱，去掉能认出真实学校、姓名的标识。

## 项目与契约

目录布局、ID、`shots.json` / `refs.json` / `review.json` / `drama.json` 字段、机械门 G00–G53、自动决策默认表、续跑与收回：[pipeline-contract.md](references/pipeline-contract.md)。开工先读它，全程按它对账。各阶段审查问题、分级与输出格式统一在 [review-checklists.md](references/review-checklists.md)；多剧总览、导出资料、决策记录与规则冲突优先级见 [project-hub.md](references/project-hub.md)。

## 阶段与门

写作阶段（A0–E）可多集并行；生产阶段（F–J，含 G2 预演粗剪）按阶段顺序推进，阶段内的生成按硬约束 2 的槽位并发。每阶段：读对应参考 → 产出 → 跑门 → 修到 0 error → reviewer 子代理（C、E 两阶段）→ 下一阶段。

| 阶段 | 做什么 | 读 | 产出 | 门 / 命令 |
|---|---|---|---|---|
| A0 原著拆解（仅改编项目） | 用户给的是小说、网文或多集原稿时：材料前提与入口判断、章节/分集精确索引、逐章功能提取、剧情单元聚合、人物归并、改编价值判定与分集候选，再立改编契约（删线、合并、换载体） | [adaptation.md](references/adaptation.md)；长篇另读 [series-long-form.md](references/series-long-form.md) | `项目开发/原著分析/`、`项目开发/改编契约.md`（模板 `assets/templates/改编契约.md`） | `novel_index.py index/verify/coverage`、`episode_intake.py index/verify/slice`；reviewer 按 review-checklists §R |
| A 立项 | 先查市场爆款题材库定首发平台与形态，再出 ≥6 个机制不同的候选（每个标注对标爆款与长青度）、按爽感检查表打分选一（饱和设定可以用，但必须写清新在哪里）；再四问定爽点、选一个主类型、人物与反派手段、装置条款、分集走向；写一行可生成性预算（台词角色、主场景、接触镜数）；选画风 `style_preset` 并全剧锁定，按画风选视频头句；定 `ai_label` | [market-hits.md](references/market-hits.md)；[premise-novelty.md](references/premise-novelty.md)；[story-engine.md](references/story-engine.md) §0–4、§10；[genre-cards/索引.md](references/genre-cards/索引.md)（选定主类型后读对应题材卡）；[styles.md](references/styles.md) §1；超过一季、集数多或续季读 [series-long-form.md](references/series-long-form.md) | `项目开发/系列简报.md`（含 `## 立项候选`、`## 爽感打分`）、`drama.json`（含 `style_preset`、`style`、`video_prompt_head`、`ai_label`） | 模板方括号清零；候选 ≥6 且打分表在（`next` 缺了会 warn）；`project_tool.py next` 不再指 A；G33、G36（视频头句）、G39；reviewer 按 review-checklists §A |
| B 情绪集纲 | 每集一行：受什么气、底牌与谁先知道、主角行动、反派失去、兑现、新问题、交接事实 | story-engine §5–6、§8；长篇的分集卡与跨集记忆见 series-long-form §4–5、§8 | `项目开发/情绪集纲.md`（长篇另有 `项目开发/跨集记忆.md`，模板 `assets/templates/跨集记忆.md`） | 每格具体；反派失去非空；reviewer 按 review-checklists §B |
| C 剧本 | 集纲那一行扩成可拍剧本；台词多、反应快、按用途写，单句短（拆句是为了句数多）；台词用目标语言母语口语直接写（一人称、称谓、敬语、语气词），专名标读音；每句台词带情绪标签；每个事件先写起因拍、关键物品先写来源拍；每场 `[连续性]` 末尾写 3–5 条「必拍：」；能力规则讲清一次后只提醒；表演写成"接住对方 → 改变局面"的动作；按单集秒表放落点，集尾与下集开头成对写 | [screenplay.md](references/screenplay.md)（§1 格式、§1b 现成剧本规范化、§2 秒表、§2b 必拍事实、§4 短、§4b 情绪、§4c 本地化、§5 动作、§5b 因果与事件起因、§5b3 能力只讲一次、§8b 集间接缝、§9 分遍修订） | `EPxxx/剧本.md`（骨架 `assets/templates/剧本.md`） | `screenplay_lint.py <项目> <EP>`（格式）；`shots_tool.py check`（G16、G37 剧本部分先跑：新建空 shots.json 也能报剧本门）；reviewer 子代理按 [review-checklists.md](references/review-checklists.md) §A–C 审（含母语审读、事件起因、关键物品三问、C10 合规），两轮内清 Major |
| D 视觉设定 | 人物/地点/道具条目、锚点、音色、锁、身高与尺度锚点（厘米身高 + 头身比）、每个主场景一行平面图与动线；有台词的主要人物加头肩身份图 `IMG-<NAME>-FACE`；refs.json 增量 | [visual-assets.md](references/visual-assets.md)（§4b 空间逻辑、§12 尺度）、[image-prompts.md](references/image-prompts.md)（refs.json 的 `prompt` 怎么写）、[styles.md](references/styles.md) | `EPxxx/视觉设定.md`（骨架 `assets/templates/视觉设定.md`）、`参考图/refs.json` | `shots_tool.py check-refs`（G18–G20、G34；头肩图免全身/身高 warn）；`visual_lint.py`（V01–V06）；reviewer 按 review-checklists §D |
| E 分镜与提示词 | 每镜职责、起点与终点、必要身份/空间锚点、台词与表演；同一个人的连续戏合并成长镜头（拆就写 `split_reason`）；说话镜写 `gaze`（看对手、方向与对手位置一致）；事件镜 `requires_setup` 指起因镜、关键物品有来源镜或插入特写；插入/冲击镜过短写 `fast_cut_reason`；台词 `lang`、`reading`；参考图按功能分工；动作计划用 `planned_action_window`，跨正反打事实可用 `scene_state`；每场 `must_show` 照抄剧本「必拍：」、承担镜写 `must_show_ids`，数量类把数字和排布写进 frame_prompt；解释能力的镜标 `explains_ability`；对白镜 motion 写承接动作 | [storyboard-keyframes.md](references/storyboard-keyframes.md)（§2c 一眼看懂、§2e 必拍事实、§4 视线、§6b 道具布局镜、§7b 长镜头、§7c 节奏下限、§8c 承接与能力重复）、[video-prompts-general.md](references/video-prompts-general.md)（§3b 长镜头写法）、[video-prompts-h3.md](references/video-prompts-h3.md)（用户指定 Seedance 时改读 [video-prompts-seedance.md](references/video-prompts-seedance.md)） | shots.json 与渲染分镜 | 机械门无 error（G46 必拍事实覆盖是 error；G42–G45、G47–G49 是 warn，逐条判断）；warn 结合叙事判断，不能靠堆提示词消警告；`visual_lint.py`；reviewer 按 review-checklists §E |
| F 参考图 | 身份图、底板、道具图 | visual-assets §7–8、§4b、§12、image-prompts §3–4、§9、[production-and-review.md](references/production-and-review.md) §4；走官方接口时读 [providers.md](references/providers.md) | `参考图/IMG-*.png` | `produce.py refs`；模型 查看每张 PNG 目检（底板必答"空间说不说得通"、尺寸是否现实），不过 `--retake` |
| G 起始帧 | 每镜起始帧 | production-and-review §3–4 | `起始帧/F_*_t*.png` | 先金丝雀一镜；`produce.py frames`；逐张目检（一人、朝向、持物、留空、无字、像参考，加 production-and-review §4b 细节与比例清单 9 项）；`review_tool.py mark <项目> <EP> <SID> --frame-take N --evidence "具体观察"`（绑定起始帧 sha，`produce.py videos/all` 提交前查） |
| G2 预演粗剪 | 起始帧全部通过后、提交视频前（金丝雀一镜除外），按镜序和计划取用时长把起始帧拼成带临时对白（草音或字幕）、标出动作起止与反应拍的粗剪，按时间看完复述情节、逐条核必拍事实和对白反应节奏 | production-and-review §3b；模板 `assets/templates/预演.md` | `审查/<EP>-预演.mp4`、`<EP>-预演.jpg`、`<EP>-预演.md`（都留档，重做另存 -v2） | `review_tool.py animatic`；查看接触表逐条答（情节点、必拍事实逐条"看得到"、对白与反应节奏、能力是否重复、一眼看懂、视线、碎切、时长差）；有"看不到"或必拍事实只靠台词回 E 或 G；animatic 生成的 `<EP>-预演.md` 按模板补齐逐条答案（每条必拍事实写秒数和看到了什么）后，首行「结论：待填」才能改成「结论：PASS」；`next` 和 `produce.py videos/all` 都按当前分镜与起始帧重算「预演输入指纹」，首行不是 PASS、模板【】没填、「## 必拍事实」表缺某条的「镜号 · 秒 · 看得到」行、有灰卡占位、预演 mp4 不在或起始帧/分镜在预演之后改过，一律不放行，要重跑 animatic；`预演指纹` 与 `预演输入指纹` 两行不删不改 |
| H 视频 | 在授权批次内生成；ASR 标出差异，先听审再决定是否重拍；另配音的，语言参数 = 台词语言、参考音频是同语言母语者，听感五问含口音与句尾语调 | [production-and-review.md](references/production-and-review.md)（§10 配音）；官方视频/语音/配乐接口读 [providers.md](references/providers.md)（`providers.py`） | 视频与候选检查 | `produce.py videos --asr` 不凭分数自动重拍；ASR 读错专名或识别成别的语言（"语种疑似不符"）即不合格 |
| I 审片 | 对具体 take 看画面、听声音、核连续性；测动作和对白区间，记录证据；逐镜核必拍事实；声音分三项记 | [quality-contract.md](references/quality-contract.md)、production-and-review §5、§5c、review-checklists §F–J | review.json 每 take 的 assessment/edit/verdict、每镜 `must_show_check`、`asr_ok` / `listen_ok` / `sync_ok` | 未审、失败或过期记录不能进正式剪辑；草剪显式用 `--draft`；`must_show_check` 有 fail 时 verdict 只能 retake 或回剧本/分镜改；"台词能解释/观众数不出来"不能放行；声音三项 null 如实写"未验证"；有镜内台词的镜还要 `--speaker-face-ok true`（纯视觉，带 evidence）；批 ok/weak/mute 要求账本来源（`jobs.jsonl` 有收回该文件的记录，生成后提示词和起始帧没改过） |
| J 剪辑 | 删镜、改剪点前先做因果自检（must_show 与 requires_setup 还在）；取用（出点包住动作、入点不切进台词或语气词、不低于节奏下限）、字幕（行长、阅读速度、数字专名不断行、以成片可听内容为准）、叠加（系统面板按 `overlays.panel` 主题出科技感样式，不压脸和眼，长文字分屏）、声音设计（底噪、音效、白光、配乐另做）、响度与真峰、片尾无拖尾停帧、AI 生成标识、成片；最后从最终 MP4 做成片终验 | [edit-and-delivery.md](references/edit-and-delivery.md)（§2d 因果自检、§2e 台词边界、§3 字幕、§4b 叠字排版、§5 声音、§7 交付核对、§7b 成片终验）；模板 `assets/templates/成片终验.md`；多剧总览与导出读 [project-hub.md](references/project-hub.md) | `成片/EPxxx.mp4`、`成片/EPxxx.overlays.json`、`剪辑单.md`、`审查/<EP>-final-qa.json`、`<EP>-final-qa.md`（脚本写）、`<EP>-成片终验.md`（模型写） | `hub_tool.py measure`（交付数字）、`hub_tool.py grade`（接镜调色，可选）；`cut.py`（`ai_label` 自动叠在前 3 秒；剪辑单标过短镜和同场平均镜长；`cut.py --panel-demo` 预览面板）；`final_qa.py <项目> <EP> [--video PATH]` 写终验机读部分（PASS 退出码 0，REVISE 退出码 2）；交付核对五步（edit-and-delivery §7）；**完成标准**：`final-qa.json` 结论为 PASS、`delivery` 为 true（对 `成片/<EP>.mp4` 跑的）、记录的 sha256 等于当前成片（`final-qa.md` 由脚本写，手改无效），`成片终验.md` 首行「结论：PASS」；或 `成片终验.md` 写「结论：REVISE」、列明已知问题，并附用户看过问题清单后点到问题编号的原话（总则 7）。拿不到用户原话 = 未交付；剧情事实类缺陷不能靠用户确认放行；`--draft` 草剪永远不算成片。REVISE 的集，`project_tool.py next` 核对「用户确认：D-xxx」在决策记录里是 `拍板人: 用户` 且原话非空才放行 |

## 每次执行

首次立项、首集预演及首集交付时，按 [观众验证与规则迭代](references/audience-feedback.md) 更新系列简报中的验证计划与决策记录。评分只支持选择试做方案；没有真人反馈就写“观众未验证”，不得造数据，也不因无人反馈阻断已授权批次。新增批次仍受原授权边界约束。

1. `project_tool.py status` 看全貌，`next` 定位阶段；读 `项目开发/决策记录.md` 和上一集的 `[连续性]`（三回锚：本批任务、上一批结束状态、当前规则）。
2. 做当前阶段，集中取得机械检查的完整诊断，再修 error；C/D/E 默认运行 `python3 scripts/stage_checks.py <项目> <EP> --stage C|D|E`（选当前阶段），一次调用按顺序执行本阶段既有检查，失败不短路，stdout/stderr 和退出码完整返回。同项目不并发跑会更新提示词或写账本的检查。该入口不替代 reviewer、不签发阶段 PASS；C 阶段分镜尚未完成的诊断仍保留，按原阶段门判断，不自动豁免。集中修复后重跑受影响的检查；同一执行期间输入与检查工具均未变的已完成检查无需重复运行，缺结果或不能确认依赖未变则重跑。warn 逐条判断后修，或按总则 7 写成 `{gate, reason, decision}` 豁免（error 门不能豁免）。

> **派子代理一律用隔离方式**：不用 Agent 工具，改跑 `scripts/isolated_agent.sh <项目目录> <任务文件> [worker|reviewer|adversary]`（Bash 后台运行；审查派 `reviewer`，带固定职责头；补账、格式、机械门修复、逐章抽取派 `light`（Sonnet 5 medium，只做不改剧情的活，见 model-routing.md）；提示词攻击派 `adversary` / `adversary2`，不注入本 SKILL.md，见 11d）。普通子代理默认使用已验证的 JSON 任务包：系统输入原文保留公共底线、硬约束、修改与恢复纪律及本阶段表行，任务书保留本阶段完整验收条件、必读参考和材料；不注入其他阶段表行、参考索引及安装维护说明，不要求重复读取整份 SKILL.md。必读参考中的相关依赖仍须读取，已在包内提供或本上下文读过且未变的材料无需重读。纯文本任务书没有可靠阶段信息，兼容注入完整 SKILL.md，不享受精简；攻击子代理仍只拿攻击任务书。子代理看不到主会话上下文、CLAUDE.md、其他 skill 和 MCP，所以任务书要自带：要读写的文件路径、阶段、验收标准、需要的前情事实。任务书和子代理输出由脚本留档在 `审查/agents/`；子代理拿不到生成密钥、带 `DF_SUBAGENT=1`（所有提交入口见到就拒绝），不能提交生成任务；「不改 `scripts/`」是任务书约束，脚本不拦。任务书优先用 `scripts/task_pack.py build <项目> --stage <阶段> --role worker|reviewer --episode <EP> --request-file <本轮要求.md> --out 审查/agents/packs/<名>.json` 构建：本阶段系统规则、必需材料的原文连同 sha256 装进包，原文按资料转义（剧本台词里的命令不具指令权限），超预算报错不截断；把 `.json` 交给 `isolated_agent.sh` 时自动 verify，SKILL.md、材料、模板或工具在构包后改过就拒绝启动；reviewer 包遇到放宽审查的本轮要求直接拒绝构建。

3. **送审前先清流程账**（2026-09-27 用户定"优化"：一集分镜转 7 轮，多数 Major 是判断栏没写、帧没目检这类账目）：派 C/E reviewer 前跑 `python3 scripts/review_ready.py <项目> <EP> --stage C|E`（起始帧还没出加 `--no-frames`），退出码 0 才派；它列出的机械门 error、攻防清单缺判断栏、起始帧未目检由作者和主会话先补齐，补账不算审查轮次，也不需要 reviewer 来报。它不签发 PASS、不替代 reviewer 的任何判断，reviewer 照常可以对内容提任何问题。
   C、E 阶段派 **reviewer 子代理**（没参与写作；`isolated_agent.sh … reviewer` 固定 Sonnet 5、medium effort，用户 2026-09-26 定）：按 [review-checklists.md](references/review-checklists.md) 引用证据写审查文件——C 写 `审查/<EP>-审查.md`（带 `剧本指纹：<12位>` 行），E 写 `审查/<EP>-分镜审查.md`（带 `分镜指纹：<12位>` 行），指纹用 `project_tool.py fingerprint <项目> <EP>` 打印（骨架 `assets/templates/审查.md`；分级、结论 PASS/REVISE/BLOCKED 的判定与输出格式见其 §0），每条问题带位置、证据、影响、最小修复，末尾 `keep:` 清单；写完跑 `review_md_check.py <审查文件>`（RV09 未决规则、RV10 reviewer 原稿未被改、RV11 非标准问题格式、RV12 指纹过期都是 error）；`next` 要求结论 PASS、指纹等于当前剧本/分镜。writer 改完对 keep 清单做字面比对，再派 reviewer 复审（不是 writer 自己勾掉）。同一 Major 两轮没过：按 reviewer 的修订建议原样改，再复审一次；Blocker 和剧情事实类 Major 不能记未决，仍不过就停下报告用户，其余按总则 7 记未决后继续。
4. 生产阶段用少量样片覆盖身份、接触、长对白等实际风险；先预演粗剪再批量视频。重拍先诊断、受授权预算限制；take 用尽仍缺关键情节时暂停正式成片并改分镜，不能自动 weak 放行。
5. 每集出成片后：每秒抽一帧拼网格找可疑处，可疑处和每条必拍事实抽单帧看原图（镜序、人物、叠字位置、前 3 秒 AI 标识），网格和抽帧存进 `审查/`、每条写格位秒数和看到了什么；整片跑一遍 ASR 核对全集台词（edit-and-delivery §7），再跑 `final_qa.py` 并写成片终验 `审查/<EP>-成片终验.md`（§7b，结论 PASS，或列已知问题等用户原话确认，等到之前该集算未交付）；汇报时声音结论按三项写，未听审就说未听审；`project_tool.py status`，把决策、未决、weak 镜写进决策记录；按已授权的 Git 交付策略同步，汇报成片路径；授权范围内继续下一集。
6. 全部集完成后汇报：每集时长、镜数、重拍次数、weak/drop 镜、未决项、未交付项、决策记录摘要；数字取自 `project_tool.py status` 与账本输出，原样贴，不手写。每次交付另列“制作验收 / 声音验证 / 观众验证”：脚本 PASS 不代表真人听审或商业效果通过，具体口径见 audience-feedback §3。用现有账本记录可用成片分钟成本、人工介入时间与返工原因；缺数据写未知。

## 自动决策（不问人）

创作配置默认 general，不替用户选择复仇或异能。commercial_fast 才启用密对白与快反应参考；规模和时长作为可修改计划，模型与尺寸须明确。ASR 不设自动放行线；take 用尽需判断缺陷是否影响核心故事。

## 修改纪律

- 改一拍，连读三拍：改过的镜头前后各一镜一起重读边界链（G26）。改的是事实（数量、金额、时间、地点、谁拿着、谁知道）时，影响范围按事实传递查，不止前后一拍：全剧 grep 这条事实和由它推出来的东西（余额、倒计时、谁因此行动），剧本、跨集记忆、shots.json 的 must_show 和提示词逐处核对，改不动的列出来报告。
- 修门只改诊断出的那一项；不往提示词里堆负面词（点名否定的写法见 video-prompts-general §2b）。修门是把内容改对，不是把字段填满：用空话、同义改写或改 `kind` 之类让门不再检查，都算没修（总则 9）。
- 台词只能在剧本阶段改；分镜和提示词阶段发现台词装不下，先加秒数（同一个人就写成一个长镜头，上限 `shot_seconds.max`），仍装不下再回剧本合并同质节拍；换人说话才拆镜。
- 语速：`drama.json` 的 `speech_rates` 是估算值，第一集 ASR 出来后用实测（词级时间）校准，写回配置。
- 模型行为先记账再立规矩：实测写进 `项目开发/模型观察.md`；成功三次只构成候选经验，不自动升级规则。按 audience-feedback §4 对比旧写法、记录失败与混杂因素、限定模型和镜头范围，并写复核或撤销条件。生产中只记观察；修改 skill 需另有用户授权，不为当前素材放行改门。

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

`python3 scripts/selftest.py`：起假中转把整条链离线跑一遍（含提交恢复回归、G36–G53、预演、父帧、AI 标识、面板渲染与入场动画、剪辑单节奏统计）。需要 ffmpeg/ffprobe、Pillow、requests；cut.py 避脸和 final_qa.py 压脸检测另需 OpenCV（`opencv-python-headless`，可选：没装时照常出片，剪辑单写"未做避脸"，终验压脸项写未验证）；只有显式设置 `SELFTEST_ASR=1` 才测 ASR，模型需已缓存在本地。只测提交与恢复可运行 `python3 scripts/client_selftest.py`，不需要 ffmpeg/Pillow。

无 ffmpeg/ffprobe 时可运行 `python3 scripts/selftest.py --no-media`，覆盖初始化、机械门、渲染、假中转生产与续跑；不验证真实视频解码、预演、ASR 或剪辑。

`python3 scripts/merged_selftest.py`：合并进来的新工具离线自测（`hub_tool`、`providers`、`visual_lint`、`screenplay_lint`、`review_md_check`、`novel_index`、`episode_intake`），不起中转、不调用付费接口，有 ffmpeg 时顺带实测 `hub_tool measure/grade`；只跑其中一项用 `python3 scripts/merged_selftest.py <名字>`（或 `-k <名字>`）。`python3 scripts/quality_selftest.py` 测语义筛查、take 审片记录、剪辑准入与场景状态。
