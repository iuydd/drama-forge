# 合并台账 · 视觉 lane（视觉资产、图片提示词、分镜）

来源：`short-drama-assets`、`short-drama-image-prompts`、`short-drama-storyboard` 三个子 skill 的全部文件。
落点缩写：VA = `references/visual-assets.md`，IP = `references/image-prompts.md`（新建），SK = `references/storyboard-keyframes.md`，TPL = `assets/templates/视觉设定.md`（新建），VL = `scripts/visual_lint.py`（新建），MS = `scripts/merged_selftest.py` 的 `test_visual_lint()`。

通用取舍（三个来源都适用，下文不再逐条重复）：
- **逐步请创作者确认**（creator_acceptance、pending_choice、预览→确认→重写、"交给创作者选"）与 drama-forge 全自动冲突 → 改写为岗位（character-designer / art-director / director / script-supervisor）自动决定 + `项目开发/决策记录.md` 一行记录；含混指代改为"script-supervisor 标出、编剧改剧本"。仍需用户的只有付费授权和模型选择（SKILL.md 硬约束 1、1b）。
- **结构化 JSONL 管线**（`sources` 声明记录、`src/record_id` 引用解析、`schema_version`、`destination`、`example_only`、`creator_acceptance`、`authority:candidate`、`REF-/PLAN-` 槽位语法、`IMG-/SHOT-/LOOK-/VIEW-/PSTATE-` ID 体系、五文档 `creator_markdown_check.py`）→ 不搬：drama-forge 的数据契约是 `drama.json` / `shots.json` / `refs.json` / `视觉设定.md`（pipeline-contract），两套结构不混写。其中有价值的"语义"已按 drama-forge 字段改写（见各条）。
- **规则分级表**（structural_invariant / reviewed_invariant / craft_default / taste_option）→ 不搬分级体系；drama-forge 用 G 门 error/warn + reviewer finding 表达同样的轻重。
- **"见 $short-drama-xxx" 指向**：全部改写为 drama-forge 内部章节引用，无残留。

## short-drama-assets

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 身份/变体/镜头瞬态/故事语义四分；工作流 8 步；画面代称规则（多语言、同形词写"无"）；持续身体—物件关系写进状态 | 四分与三问：重复已有（VA §2）。画面代称细则、别名 → VA §1b。持续关系 → VA §5b、SK §5。工作流步骤 → VA §1–§6c 已覆盖；"创作者确认/末端回报"按通用取舍改为自动+决策记录 |
| `agents/openai.yaml` | 平台显示名与默认提示 | 不搬（平台元数据；drama-forge 有自己的 `agents/openai.yaml`） |
| `references/stage-contract.md` | AST-01…13、CON-01…07 规则表 | 语义已分散落到 VA §1b、§2b、§3b、§3d、§6、§6b、§6c、§13；规则编号与分级体系不搬（通用取舍） |
| `references/occurrence-extraction.md` | 六问（已有）；出现方式四类 on_screen/voice_only/represented/mentioned_only；set_dressing；群体称谓；含混指代四种情形；一个动作句带出多种资产的示例；事实分层；完整性检查 | 六问：重复已有（VA §1）。四类出现方式、布景、群体、动作句示例、含混指代 → VA §1b。完整性检查 → VA §13。事实分层表是 JSONL 字段用途 → 不搬（通用取舍） |
| `references/identity-vs-variant.md` | 四种结论 reuse/new_variant/new_asset/unresolved；三类资产身份—变体表；是否值得建变体四问；年龄段/不同演员、同址空间、同款多件、不可逆改造、持续多集大状态；命名分层与版本后缀；决定记录字段 | → VA §2b（表、四问、易误判、命名、决策记录）。双胞胎/伪装：重复已有（VA §2）。同款多件：重复已有（VA §5） |
| `references/character-and-look.md` | Character/Look 分层；Look 内容与互斥；侧/背锚点（已有）；全组身高次序（已有）；关系不决定美丑（已有）；制作形态决定识别通道表；痣疤既定特征保持；形态不改身份事实；模板槽位（已有）；画面代称要覆盖每种正文语言；群演颗粒度 | Look 分层与互斥、痣疤 → VA §3b。识别通道表与"形态选通道不改身份" → VA §3c（并在 IP §7 写提示词侧对应）。模板句、身高、美丑、侧背锚点：重复已有（VA §3）。画面代称多语言 → VA §1b（本项目提示词固定英文，只需一个拼写）。群演 → VA §1b。声音段落 → 见 voice-direction 行 |
| `references/location-and-view.md` | Location/View 分工；何时建 View；新 Location vs 同一 Location；光/天气/陈设必须有来源；停电视图示例；检查问题 | → VA §4c。"先画脑内平面"：重复已有（VA §4b 平面图与动线）。空场政策：重复已有（VA §4 默认空场、G19） |
| `references/prop-and-state.md` | 道具身份/状态字段（已有）；人物—物件持续关系；个体/同款/集合（已有）；四类文字政策（已有）；现实品牌由创作者决定；敏感屏显；内容物与知情（已有）；关键道具完整过程；铁皮匣反例 | 持续关系、关键道具过程 → VA §5b。铁皮匣反例、剧情标签不是锚点、内容物不消失 → VA §5。敏感屏显、逐字保存 → VA §9。**现实品牌"交创作者决定" → 不搬**：与 drama-forge 自动规则"现实品牌默认虚构化"（VA §10）冲突，以 drama-forge 为准 |
| `references/voice-direction.md` | 参考音频是音色载体；预置音色合成参考；身份 vs 表演一句话判定；参考借用边界（情绪、录音空间、背景永不借）；绑定≠听过（admission_status）；选型判据 3–5 条带反例；写出区分度（最易混角色）；预置音色对比试听；专名读音一种拼法；声音变体 | → VA §3d（全部要点改写），TPL"声音方向"行。**"不要用文字描述冒充音色身份"部分不搬**：与 drama-forge 硬规则冲突——H3 首帧模式挂不了参考音频，refs.json `voice` 文字描述是逐镜保持音色的唯一手段（G21）；改写为"文字描述 + 参考音频两个载体各司其职"。专名读音：重复已有（`drama.json` readings、G44）。"TTS 由 produce 技能在确认后执行" → 改为 drama-forge 的配音流程（production-and-review §10）与成本边界 |
| `references/continuity-delta.md` | 边界匹配（已有 G26）；状态表 vs 变化记录；各环节负责什么；五组状态；写变化记录七步；未知≠默认（已有）；知道≠知道对方也知道；有来源≠合理；合成状态链；非线性时间；修订影响；交接检查 | 五组状态、七步、有来源≠合理、互知、非线性时间、修订影响、转手、集间交接 → VA §6c。未知≠默认、边界匹配：重复已有（VA §6、SK §5、G26）。知情分层另见 scene-state-and-reveal（已有）。闪回：以 SKILL.md 硬约束 6b 为准（标清时间视角） |
| `references/continuity-lock.md` | 为什么锚点不够；上锁三条件（已有）；锁面最小名词短语（已有）；粘词不算、否定不算；一实体一锁；范围按实际出现写；参考图也带锁面；状态不进锁面；反例；中文锁面与英文正文不匹配 | → VA §6b；粘词检查 → VL V04（G23 已挡否定式）。锁的 JSON 写法：重复已有（VA §6 `locks`）。视觉设定里的锁行语法 → TPL（按 drama-forge `locks` 字段改写，不搬 `LOCK-…《》（镜头：…）· 锁面：` 严格语法与 `creator_markdown_check.py`）。视频提示词也须带锁面：属视频 lane，未改 video-prompts-* |
| `references/asset-review-checklist.md` | 机械检查/语义审查/craft 默认/taste 选项/创作者确认五层清单；完成判据 | → VA §13（机械 + 语义 + 可调默认；finding 写法）。"创作者确认"层按通用取舍改为决策记录 |
| `assets/character-look.example.jsonl` | Character/Look JSONL 示例（含 voice_direction 结构、not_identity、not_voice_identity） | 语义已进 VA §3b、§3d 与 TPL；JSONL 结构不搬（通用取舍） |
| `assets/continuity.example.jsonl` | 变化记录 JSONL（before/after/cause/effective_range/affected） | 字段语义 → VA §6c、TPL"状态变化"行；JSONL 不搬 |
| `assets/decisions.example.jsonl` | 复用/新变体/新资产决定记录 JSONL | 字段语义 → VA §2b "决定写进决策记录"；JSONL 不搬 |
| `assets/location-view.example.jsonl` | Location 与 View 记录（spatial_identity、orientation、state_differences） | 语义 → VA §4c、TPL"视图"行；JSONL 不搬 |
| `assets/occurrences.example.jsonl` | 出现记录（presence、production_disposition、candidate_bindings、ambiguity） | 语义 → VA §1b；JSONL 不搬 |
| `assets/prop-state.example.jsonl` | Prop 与 PropState 记录（identity_anchors、text_policy、custody、contents） | 语义 → VA §5、§9、TPL"道具"段；JSONL 不搬 |
| `examples/minimal/characters.jsonl` | 最小人物记录样例 | 不搬（JSONL 样例；drama-forge 样例在 `assets/example/`） |
| `examples/minimal/looks.jsonl` | 最小造型记录样例 | 不搬（同上） |
| `scripts/asset_check.py` | 校验 characters/looks JSONL 的引用解析、必填字段、接受状态 | 不搬：校验对象是 drama-forge 不使用的 JSONL 结构；drama-forge 相应检查由 G18–G20、G23–G26、G34 与 VA §13 承担 |
| `scripts/selftest.py` | asset_check 的自测 | 不搬（随 asset_check 一起不搬） |
| `scripts/__pycache__/asset_check.cpython-313.pyc` | 编译缓存 | 不搬（生成物） |
| `references/.omc/state/sessions/*/pre-tool-advisory-throttle.json` | 插件运行状态缓存 | 不搬（非技能内容） |

## short-drama-image-prompts

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 用途先定；八段写法；参考槽位用途；锁面进正文；正文不含占位与流程说明；尾帧状态图由 IMG 条目承载；提示词语言跟项目 | 用途与一图一问 → IP §1。八段：重复已有（VA §7）。锁面进参考图 → VA §6b。正文纯净 → IP §2。尾帧状态图 → IP §3.8、SK §5b。语言：drama-forge 固定英文（G18），不搬"跟随 prompt_language" |
| `agents/openai.yaml` | 平台元数据 | 不搬 |
| `references/stage-contract.md` | IMG-01…14 规则表 | 语义已落到 IP §1–§9、VA §4c、§8；规则编号不搬（通用取舍） |
| `references/common-recipe.md` | 四个篮子；锚点选择启发；按产物类型裁剪；文字两层（来源政策 → 呈现方法）与映射表；签名字形；输入参考图检查状态；参考图能决定什么；负面约束；审美语言；光学与表面；失败征兆 | 四篮子、锚点启发、审美词、正文纯净 → IP §2。参考图用途边界、输入参考必须看过 → IP §1、VA §8。负面约束只写本张风险 → IP §3.1。文字呈现映射 → IP §6，**其中 `readable`（生成可读字）不搬**：与硬约束 4"生成画面不出字"冲突，改为后期叠加/空白承载面。签名字形 → IP §6。八段顺序：重复已有（VA §7） |
| `references/character-and-look.md` | 身份板只画一套相容 Look；身份层与 Look 层；四种构图（身份板/面部板/服装板/状态板）；参考友好性；写作顺序；不假精确；变体只写 delta；形态投影与模板槽位 | 一套 Look、写作顺序、排除 → IP §3.1。面部板：重复已有（VA §3 `-FACE`），写法补充 → IP §3.2。状态板 → IP §3.4。形态投影 → IP §7。模板槽位、不假精确：重复已有（VA §3、§7） |
| `references/location-plate.md` | 地理测试；Location/View；文字地图；必要层次 6 项；两两关系+视线终点；1–3 强锚点；光线连续性；跨 View 同光清单（主光、色温、光比暗区、灯具开关）与允许差异；empty_stage 三档；气氛翻译；形态投影 | 层次、锚点、气氛 → IP §3.5。跨 View 对光清单与"改光要一起改" → VA §4c。形态投影 → IP §7。**empty_stage 的 preferred/not_required 两档不搬**：与 drama-forge 底板必须 `No people`（G19 error）冲突，只保留"空场"默认 |
| `references/prop-plate.md` | 道具身份与 State；八步配方；中性尺度参照；一张一个明确状态；文字四呈现；形态投影（识别结构不可省） | → IP §3.6、§6、§7。道具身份/状态二分：重复已有（VA §5）。不用剧中人手当参照：与 G19 `no hands` 一致，写进 IP §3.6 |
| `references/look-and-state-variant.md` | 何时需要变体；Base—delta—validity 六问；三类变体写法；变体 plate vs edit；失败征兆 | → IP §3.4（六问、差异要有边界、差异写在最显眼处、一张一个状态）、IP §4（edit 区别）。reuse/variant/new/unresolved：见 VA §2b |
| `references/edit-and-revision.md` | 有界编辑四项（目标/变化/保留/连续性影响）；动词纪律（已有）；每轮重复保留清单（已有）；自然语言修订的预览—确认流程；文件冲突时不覆盖 | 四项、拆细、上游事实不走编辑、删人示例 → IP §4。动词与保留清单：重复已有（VA §3、§7），IP §3.4/§4 细化。**预览→确认→重写流程不搬**（通用取舍），改为自动执行 + 决策记录；冲突合并原则保留 → IP §4 |
| `references/production-sheet-recipes.md` | reuse_job；角色/场景/道具参考板可选记录格式；布光服务识别；社会处境要有依据；多视图设定板只用于目检和裁单格、不直接挂首帧、横幅 2:1、无标签；布光词汇表（按要比较什么，不按身份标签）；伪装期判断例；首帧合成的参考 role 写法；局部修改例句；资产范围决策；反模式（表单直贴、无语义命名、名字对不上） | 多视图/转面板与裁格 → IP §3.3（新增 `layout: multi_view`、`crop_from` 约定）+ VL V01、V06。布光表 → IP §5。reuse_job → IP §1（写进 `controls`）。局部修改例句 → IP §4。反模式 → IP §9。首帧参考 role 写法：重复已有（VA §7 分工句）。资产范围决策：重复已有（VA §2b、§5）。**风格标签【真人风格，写实风格】前缀不搬**：与 G18 参考图提示词必须英文冲突，风格统一靠 `style` 句（在 IP §8 说明） |
| `references/lookdev-frame.md` | Lookdev 三类测试轴；测试问题；风格参考只控表面；高压帧绑真实场景与信息权限 | → IP §3.7（改为 director + art-director 自动比较、决策记录；受成本边界约束）。画风七选一锁定：以 drama-forge styles.md 为准，风格帧只在同一 preset 内细化 |
| `references/review-and-fixtures.md` | 审查方式；8 维证据量表 PASS/REVISE/NOTE；完成前结构检查；合成正例（人物、地点）；反例 A 混 Look、B 文字矛盾、C 越权 edit | 量表、finding 写法 → IP §9。反例 A/B/C → IP §9（改写为英文提示词）。正例 → IP §3.1、§3.4 的英文示例（按 drama-forge 口径重写，无可读文字）。结构检查 → VA §13、IP §9 |
| `assets/lookdev-prompts.md` | Lookdev 提示词输出模板（项目级文件） | 字段语义 → IP §3.7；模板文件不搬（drama-forge 不产出独立 lookdev 文件，结论进视觉设定与决策记录） |
| `assets/image-prompts.md` | 《图片提示词.md》输出模板（结构化管线） | 不搬：drama-forge 的 `图片提示词.md` 由 `shots_tool.py render` 从 refs.json 生成 |
| `assets/lookdev-frame-spec.jsonl.md` | Lookdev 规格 JSONL 填写模板 | 不搬（JSONL 管线）；语义见 IP §3.7 |
| `assets/image-prompt-spec.jsonl.md` | 图片提示词规格 JSONL 超集模板（reference_bindings、text_handling、edit 等） | 不搬（JSONL 管线）；reference 边界 → IP §1，text_handling → IP §6，edit → IP §4 |
| `examples/minimal-image-prompt-specs.jsonl` | 最小规格样例（雨衣造型人物板） | 不搬（JSONL 样例）；同类英文示例见 IP §3.4 |
| `scripts/image_prompt_check.py` | 校验规格 JSONL：引用解析、edit_delta 必填、文字政策→呈现映射、readable 与 no-text 冲突、供应商字段泄漏 | 不搬：校验对象是 JSONL；readable 映射在 drama-forge 无意义（不生成可读字，G06 已查）。改为新写 VL（V02 派生保留句、V03 改写动词、V05 质量套话）覆盖 drama-forge refs.json 的对应风险 |
| `scripts/selftest.py` | image_prompt_check 自测 | 不搬；VL 的测试在 MS `test_visual_lint()` |
| `scripts/__pycache__/image_prompt_check.cpython-313.pyc` | 编译缓存 | 不搬（生成物） |

## short-drama-storyboard

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 工作流 7 步；原生时长区间；相对时间词换算；对白估时；起点→唯一动作→终点；收尾关键帧；视觉依据/图片提示词项/输入参考图三条依据从成稿回填；REF-/PLAN- 槽位；缺图三条路；未拍场次行；无条目物件逐镜钉住并报告 | 相对时间词 → SK §5。对白估时 → SK §7e。尾帧 → SK §5b。回填参考、无条目物件、控制范围不顺延 → SK §6c。缺图不静默转文生：重复已有（VA §10），SK §6c 补"用户明确不用图才改文生"。原生时长：重复已有（`shot_seconds`、G04）。**"未拍场次"带理由省略不搬**：与 G11（剧本每场必须有镜头）冲突，不拍就改剧本。REF-/PLAN- 槽位语法不搬（通用取舍；drama-forge 用 `frame_refs`） |
| `agents/openai.yaml` | 平台元数据 | 不搬 |
| `references/stage-contract.md` | SHT-01…27、CON-01…07 规则表 | 语义分散落到 SK §2、§2d、§5、§5b、§6c、§7d、§7e、§8、§8b、§9b、§10b；规则编号不搬（通用取舍） |
| `references/shot-craft.md` | 原文落实与动作落实表（已有）；重复覆盖须带新体验；镜头目的五步；承受者反应不强制单镜；观众可见性逐事实写、用光保护身份；场面调度要素；跨轴合法手段；景别词表八档；竖屏收窄景别；切镜必有变化（已有 G27）；摄影机行为动机；对白估时；首尾成对；一镜到底还是切开（项目例外已与 drama-forge 同） | 重复覆盖、不改剧本动作 → SK §2。承受者反应、可见性、用光保护 → SK §8。跨轴 → SK §3。景别词表、竖屏、摄影机行为 → SK §7d。对白估时 → SK §7e。首尾成对 → SK §5b。动作落实表、切点变化、长镜头例外：重复已有（SK §2、§7、§7b，G27、G45） |
| `references/production-shot-grammar.md` | 一镜一职责；编号场序-镜序；拆分规则表；建立镜头要自己挣到位置；动作顺序交接草图；镜头叙事学表；工作景别走法与客厅例；机位三栏（水平角度/高度/焦段意图）与竖屏高度更贵；戏型诊断五类；子镜密度 4–8 秒；单元时长；单集时长加总；人物反应；自检 11 条；范例（递交、拆镜、保持不动）；反模式 6 条 | 建立镜头、工作景别走法、机位三栏 → SK §7d。戏型诊断、保持不动 → SK §8b。反模式 → SK §10c。自检 → SK §10 reviewer 追问。长镜头内要有变化 → SK §7b。**编号"场序-镜序"不搬**：与 G01 `EP001-S01` 冲突。**"子镜密度每 4–8 秒切一次"不搬**：与 drama-forge 同人长镜头合并（G45）和节奏下限（G42）冲突，只保留"长镜头靠镜内调度避免幻灯片"。单集时长加总：重复已有（G14 估成片时长、差值只报告）。一镜一职责：重复已有（SK §1） |
| `references/keyframe-craft.md` | 冻结关键帧九步配方（已有）；每人写身体朝向（已有）；可渲染检查表（已有）；"与上一镜相同写一句即可"；写紧约五百字；删句测试；尾帧 SHT-17 与插值代价；start-only 起草纪律与反向提取；静物测试（已有）；提示词经济；失败例 | 删句测试 → SK §6b。尾帧与插值代价 → SK §5b。反向提取核对 → SK §6c。**"与上一镜相同写一句即可"不搬**：与 G24（禁回指词，图片模型看不到上一镜）冲突，SK §6b 明写仍须绝对事实。**"约五百字"不搬**：drama-forge 定 100–150 词、镜头句固定开头（SK §6），以其为准。九步、静物测试、可渲染检查：重复已有（SK §6） |
| `references/blocking-playbooks.md` | 竖屏多人调度与设计顺序；交付面遮挡（字幕条、控件、角标）；左右唯一读法（已有）；轴线记法三行（已有）与占位即未写；正反打配对（已有）；越轴后重新声明（已有）；单房对白策略循环；证据揭示五问；群体分区与行动能力分组；关系投影；动态对象与竞赛；观察视角须匹配机位一侧；切镜前后比较清单（已有） | 竖屏多人、单房、证据、群体、关系投影、动态对象、观察方向 → SK §9b（动态物件另见 SK §5）。交付面遮挡 → SK §8（按 drama-forge 改写：字幕/面板/印章字区域由剪辑决定，平台控件区须决策记录声明才避让）。轴线占位 → SK §3。左右读法、正反打、越轴：重复已有（SK §3、§4） |
| `references/comic-keyframe-lexicon.md` | 漫剧三层组织（事实→视觉语言投影→可读性约束）；项目级画风基底八种；叙事/对话/动作特效三类镜头词表；特效体系不混用；反模式（画风漂移、万能排除清单、类型名进正文） | 三层、三类镜头词、特效体系、反模式 → SK §6d。**画风基底八种不搬**：drama-forge 以 styles.md 七个 `style_preset` 为准、全剧锁一种（G33），不另设一套名称；焦段/摄影词在 2D 画风的替换：重复已有（SK §6b 第 8 项） |
| `references/screenplay-to-keyframe-example.md` | 洗衣房合成例：原文落实表、三镜职责、"信息变化而物理状态不变"、KEY-03 冻结、三条依据回填三点注意、连续性交接表、情绪括注一源两投影 | 信息变化而物理状态不变、重复带新信息、不改剧本动作 → SK §2。回填三点注意 → SK §6c。情绪一源两投影 → SK §6c（以台词 `emotion` 字段为唯一来源）。连续性交接表：重复已有（SK §5 boundary、G26）。完整例子本身不搬（中文冻结帧正文与 drama-forge 英文 `frame_prompt` 口径不同，已有 §6b 正反例） |
| `references/lighting-craft.md` | 光的分工；按镜头职责设计亮暗；光位 + 受光结果；参考板均匀光不是镜头打光；同场光源关系；小偏差交剪辑调色 | 重复已有：受光结果、参考板均匀光、同场光源关系与小偏差交调色都在 SK §6b 第 7 项及补充说明；剪影保护身份 → SK §8 |
| `references/scene-visual-plan.md` | 何时做场次视觉计划；比较七项（戏剧转向、观众立场、空间压力、视觉推进、摄影节奏、反应落点、声音策略）；不固定方案数；选定后只投影进镜头 | → SK §2d（改为 director 自动比较、选定写决策记录） |
| `references/coverage-audition.md` | 关键场景导演方案比较；五种真正不同的命题；比较方式；不固定宫格；创作者选择 | → SK §2d（五种命题、同一方案判据；"创作者选择"改为 director 自动选定 + 决策记录） |
| `references/shot-revision-identity.md` | 镜头 ID 身份规则：重排保留、插入新建、修订保留、拆分/合并停用旧 ID 建新、停用 ID 不复用；修订后对账 | → SK §10b（对账项按 drama-forge 的 G11、G26、G32、G40、剪辑单改写；谱系写进决策记录） |
| `references/review-and-fixtures.md` | 可直接核对的结构项；需要语义审查的项；不以镜头数/景别比例/时长差为门槛 | 结构项：重复已有（G01、G11、G24、G26 等，SK §10）；语义追问 → SK §10 reviewer 段；遮挡与小比例人物 → SK §6c、§8 |
| `assets/coverage-audition.example.jsonl` | 方案比较 JSONL 示例 | 不搬（JSONL）；语义 → SK §2d |
| `assets/coverage-template.json` | 覆盖与集时长加总 JSON 模板 | 不搬（JSONL/JSON 管线）；覆盖由 G11 与 `shots_tool.py coverage` 承担，时长由 G14 承担 |
| `assets/keyframe-prompts.md` | 关键帧提示词输出模板（结构化管线） | 不搬：drama-forge 的 `分镜.md` 由 `shots_tool.py render` 生成 |
| `assets/keyframe-template.jsonl` | 关键帧 JSONL 模板（boundary_role、camera 三栏、lens_intent、delivery_surface_ref） | 不搬（JSONL）；三栏 → SK §7d，boundary_role → SK §5b，交付面 → SK §8。其 `generic_prompt` 说明里的"与上一镜相同"同样因 G24 不搬 |
| `assets/revision-lineage.fragment.json` | 拆/并/恢复的谱系片段 | 不搬（JSON 片段）；谱系改写进决策记录（SK §10b） |
| `assets/scene-visual-plan.example.jsonl` | 场次视觉计划 JSONL 示例 | 不搬（JSONL）；语义 → SK §2d |
| `assets/shot-template.jsonl` | 镜头 JSONL 模板（audience_visibility、primary_transition、framing 三栏、camera_plan 等） | 不搬（JSONL）；audience_visibility → SK §8，camera_plan 动机 → SK §7d，framing → SK §7d；边界绝对事实：重复已有（G24） |
| `scripts/storyboard_check.py` | 集时长算术、关键帧 boundary_role、边界回指词、剧本块覆盖与双重认领 | 不搬：回指词 = G24，覆盖 = G11，时长 = G14；boundary_role 与块级双重认领依赖 JSONL 结构，drama-forge 无对应字段（原则见 SK §2 动作落实表） |
| `scripts/selftest.py` | storyboard_check 自测 | 不搬（随脚本） |
| `scripts/__pycache__/storyboard_check.cpython-313.pyc` | 编译缓存 | 不搬（生成物） |

## 本 lane 新增 / 修改的 drama-forge 文件

- 修改 `references/visual-assets.md`：来源行改写；目录；新增 §1b、§2b、§3b、§3c、§3d、§4c、§5b、§6b、§6c、§13；§5、§8、§9 补充条目。
- 修改 `references/storyboard-keyframes.md`：来源行改写；目录；§2、§3、§4、§5、§6b、§7b、§8 补充；新增 §2d、§5b、§6c、§6d、§7d、§7e、§8b、§9b、§10b、§10c。
- 新建 `references/image-prompts.md`。
- 新建 `assets/templates/视觉设定.md`（参考骨架，`project_tool.py init` 不自动复制）。
- 新建 `scripts/visual_lint.py`（V01–V06，只读）；`scripts/merged_selftest.py` 追加 `test_visual_lint()` 并在 `main()` 里加一段调用。

## 拿不准、需要主会话确认的点

1. `merged_selftest.py` 在本 lane 工作期间被别的 lane 整文件覆盖过一次（本 lane 的测试一度丢失，已重新插入）；交回时文件已被合并成按 `globals()` 自动发现 `test_*` 的版本，5 个测试（含 `test_visual_lint`）全部通过。主会话收尾时建议再跑一次确认各 lane 的测试都在。
2. refs.json 新约定 `layout: "multi_view"`、`crop_from` 只被 `visual_lint.py` 读取；`shots_tool.py check-refs` 不认识它们（不会报错，但 G18 对转面板仍按普通身份图检查，可能给"建议全身/正面"一类 warn）。是否把转面板豁免写进 check-refs，属于 shots_tool.py 的改动，本 lane 未动。
3. `visual_lint.py` 没有接进 `selftest.py` 和 `project_tool.py next` 的流程，目前靠 VA §13 提示手动运行。
4. 锁面须进视频提示词（来源 CON-07）属于视频 lane，本 lane 未改 video-prompts-*。
