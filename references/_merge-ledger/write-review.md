# 合并台账：剧本与审查 lane

来源：`short-drama-write/`、`short-drama-review/` 全部文件。本 lane 只写了：

- 修改 `references/screenplay.md`（新增 §1 格式细则、§1b、§3 反应/场域、§3b、§4d、§5 物件/空间/打戏、§5c、§7 巧合补充、§7b、§7c、§8 兑现后收束、§9 分遍修订与分批续写；§10 的 reviewer 问题移到 review-checklists 并留一句引用）
- 新建 `references/review-checklists.md`（§0 通则/分级/结论/输出格式/指令优先级/改写回归/模板感；§A–E 各阶段必答问题；§F–J 索引与观察校准；§R 原著改编分析）
- 新建 `assets/templates/剧本.md`、`assets/templates/审查.md`
- 新建 `scripts/screenplay_lint.py`、`scripts/review_md_check.py`；测试 `test_screenplay_lint`、`test_review_md_check` 写进共用的 `scripts/merged_selftest.py`

判定写法：**搬 →** 落点；**重复 →** drama-forge 已有位置；**不搬 →** 原因。

## short-drama-write

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 四种入口（有集纲 / 只有点子 / 已有剧本定点修订 / 非规范文本规范化） | 规范化入口 **搬 →** screenplay §1b；其余三种 **重复 →** SKILL 阶段表 C、screenplay §2、§9"用户原文优先" |
| 同上 | 工作流：锁承诺→只识别本集实际存在的发动机→因为-行动-结果→逐场功能→交稿前静默反查、撤掉自检长出来的机关 | 条件启用 **搬 →** screenplay §7b 开头；"撤掉机关"与经济性检查 **搬 →** §9 第 9 遍；其余 **重复 →** §2、§3 |
| 同上 | 写作要求（每场改变信息/权力/关系；对手转向要可追溯；资源不替人物完成最难的戏；事务角色不硬加戏；经济性检查；按真实朗读压稿） | 资源/事务角色 **搬 →** §3b、§7；经济性 **搬 →** §9；其余 **重复 →** §3、§6、§8 |
| 同上 | 创作者口味（台词多、单句短、即时反应、本地化、事件先有起因） | **重复 →** screenplay §4、§4c、§5b（本来就是从 drama-forge 抄过去的） |
| 同上 | 按需知识路由 | **不搬**：指向被删的子 skill 文件；内容已并入 screenplay 各节 |
| 同上 | 时长估算三条命令、计数口径（标点不计） | **重复 →** screenplay §6 + `shots_tool.py` G16/`speech_seconds` |
| 同上 | 完成判据、"资产/分镜只在用户点名时开始"、转 `$short-drama` 做跨文档核对 | 完成判据 **重复 →** §8；"用户点名才开始""转 $short-drama" **不搬**：与 drama-forge 全自动流水线冲突 |
| `agents/openai.yaml` | 子 skill 的显示名与默认提示 | **不搬**：drama-forge 有自己的 `agents/openai.yaml` |
| `references/stage-contract.md` | SCR-01 场景议程/反对/转向/退出，氛围场可豁免 | **重复 →** §3；豁免条款 **搬 →** §3 第 2 段 |
| 同上 | SCR-02 选择优先于巧合、选有表达力的场域 | 场域 **搬 →** §3；其余 **重复 →** §7 |
| 同上 | SCR-03 私密想法用行为/证据/VO 表达 | **重复 →** §4"潜台词…关键认知必须说破"、§5 |
| 同上 | SCR-04 对白带议程与变化 | **重复 →** §4；议程表 **搬 →** §4d |
| 同上 | SCR-05 标签闭合、`[连续性]` 不能断言未发生 | **重复 →** §1 模板说明；标签边界表 **搬 →** §1 |
| 同上 | SCR-06 沉默/俚语/旁白属口味 | **重复 →** §4 general 模式说明；§9"方言笨拙保留" |
| 同上 | SCR-07 生产关键事实不能混在普通文字里（reviewer 语义判断） | **搬 →** review-checklists §C3 第 3 问 |
| 同上 | SCR-08 抽象情绪译成行为 | **重复 →** §5 可表演动词 |
| 同上 | SCR-09 长发言用改变策略的动作断开，无转折就缩短 | **搬 →** §4d"同一人连说时的动作行"（与 §4"短"的拆句规则协调写法） |
| 同上 | SCR-10 可替代实现 | **搬 →** §7c（改为导演岗对生成风险高的关键拍在决策记录写备选；不等创作者标注） |
| 同上 | SCR-11 声音事实 | **搬 →** §5c |
| 同上 | SCR-12 人多的场 | **搬 →** §3b |
| 同上 | SCR-13 艰难选择两边都活 | **重复 →** §7；审查问题 **搬 →** review-checklists §C7-1 |
| 同上 | SCR-14 可争议证据 | **搬 →** §7b |
| 同上 | SCR-15 收束留余效、代价不自动复位 | **重复 →** §8；补充句 **搬 →** §8 |
| 同上 | SCR-16 精确死线 | **搬 →** §7b |
| 同上 | SCR-17 有限次数按完成状态计数 | **搬 →** §7b（加金手指次数/冷却的对应） |
| 同上 | SCR-18 动作行不以"短语："开头 | **搬 →** §1 + `screenplay_lint.py` SP08 |
| 同上 | 四级规则分级 | **搬 →** review-checklists §0.2 |
| `references/screenplay-format.md` | §1 事实所有权（剧本是唯一可编辑源，索引不回写） | **重复 →** pipeline-contract §1"创作真相是 Markdown" |
| 同上 | §2 集/场标题语法、ID 稳定、拆合场要显式映射 | 语法 **重复 →** §1；三槽检查 **搬 →** `screenplay_lint.py` SP02 |
| 同上 | §3 动作/对白/标签表（含"不应用来做什么"） | **搬 →** §1 标签边界表 |
| 同上 | §4 注释与未知内容保留 | **改写搬 →** §1"剧本里不写 HTML 注释"（drama-forge 解析器会把含冒号的注释读成对白，已实测）+ SP04 |
| 同上 | §5 完整示例（渡口售票室） | **不搬**：drama-forge 已有 §5b 例子与 `assets/example/EP001/剧本.md`；新模板见 `assets/templates/剧本.md` |
| 同上 | §6 稳定块 ID 与临时索引 | **不搬**：drama-forge 以场次 ID + 逐字台词（G10）对照，不维护块索引；与"不建第二套状态"一致 |
| 同上 | §7 规范化入口（存原稿、预览、语义变化分列、创作者确认） | **搬 →** §1b，改成自动：原稿存 `项目开发/原稿/`、语义变化写决策记录、reviewer 在 C 核对（review-checklists §C8） |
| 同上 | §8 剧本里不该出现的内容 | **搬 →** §1 |
| 同上 | §9 完成前检查 | 机械项 **搬 →** `screenplay_lint.py`；审查项 **搬 →** review-checklists §C2–C3、§C8 |
| `references/production-format-dialect.md` | 【】△▲ 制作稿格式、兼容变体槽位识别表、OS/VO 标记剥离 | **搬 →** §1b 第 2–3 条 + SP06（只用于识别和规范化；drama-forge 新稿不用这种格式） |
| 同上 | 群演概括写、点名即产生资产 | **搬 →** §1 |
| 同上 | 表演括注只留能同时完成的，独立动作拆行 | **搬 →** §1 |
| 同上 | 集标题不套句式 | **不搬**：drama-forge 集名由集纲决定，影响小 |
| 同上 | 单词行当拍（悬疑停顿） | **不搬**：taste_option，drama-forge 的节奏下限（G42）与长镜头合并规则更优先 |
| 同上 | 画外音记法表、规则VO、系统信息声画选择 | **重复 →** §1 `[VO]`/`[OS]`、SKILL 6f 系统面板、styles §12（面板一律后期叠加） |
| 同上 | 【闪回】【闪入】指令 | **不搬（冲突）**：drama-forge 顺叙优先；规范化时按 §1b 第 4 条改成当前时空交代或单独成场标清时间 |
| 同上 | 叙事工艺九条（开场切入、对峙升级、攻防回合、爽点后反应、用做法表现立场、闪回、集尾钩子、打戏、拆集边界） | 爽点后反应 **搬 →** §3"反应要承担后果"；打戏 **搬 →** §5；闪回 **不搬（冲突）**；其余 **重复 →** §2 冷开场、§3、§4、§8、§8b |
| 同上 | 项目选择表（规模从时长反推等） | **重复 →** §6、SKILL"修改纪律" |
| 同上 | 自检清单、范例 A/B、反模式九条、扩写工作流 | 反模式 **搬 →** §1b 末段；范例 B（规范化只动结构不改台词）**搬 →** §1b 第 3 条原则；自检与范例 A **重复 →** §9、§3；扩写（不改原意、新情节归原作者）**搬 →** §1b 第 6 条"不能为填字段补造剧情" |
| `references/script-craft.md` | §1 剧本任务与四级规则 | **重复 →** review-checklists §0.2 |
| 同上 | §2.1 输入事实优先于手艺，不补造精确数字/记录/机关；条件启用不是降低强度 | **搬 →** §7b 开头、§9 第 9 遍、review-checklists §C1-7 |
| 同上 | §2.2 场景存在理由、场域 | **重复 →** §2；场域 **搬 →** §3 |
| 同上 | §2.3 场景依赖检查 | **重复 →** §2"排序前问" |
| 同上 | §3 工作卡、目标可执行、反对方式、转向测试 | **重复 →** §3；氛围场豁免 **搬 →** §3 |
| 同上 | §3.4 巧合四判据、资源不替人物付款、旁人进场反应；误会四判据 | 误会与巧合核心 **重复 →** §7；资源/旁人 **搬 →** §7 |
| 同上 | §3.5 艰难选择 | **重复 →** §7；追问 **搬 →** review-checklists §C7-1 |
| 同上 | §4 意义与载体、可表演动词、生成管线常见动作、反应承担后果 | 反应 **搬 →** §3；其余 **重复 →** §5 |
| 同上 | §5.1 空间是可用关系 | **搬 →** §5 |
| 同上 | §5.2 物件进入行动链、重复要有新工作、不引入一次性道具 | 重复/一次性 **搬 →** §5；其余 **重复 →** §5 |
| 同上 | §5.3 证据四层 | **搬 →** §7b |
| 同上 | §5.4 主要配角有策略、对手筹码不自动归零 | **搬 →** §3b |
| 同上 | §5.5 人多的场 | **搬 →** §3b |
| 同上 | §5.6 主角不在场的场 | **搬 →** §3b |
| 同上 | §6 节奏来自压力变化、加速/呼吸 | **重复 →** §2 秒表、§4"快"、storyboard-keyframes §7c；呼吸要点并入 §8 兑现后收束 |
| 同上 | §6.3 倒计时、§6.4 有限单位 | **搬 →** §7b |
| 同上 | §7 动作段落、表演提示、生产标签 | **重复 →** §1、§5 |
| 同上 | §8.1 开场接住进入状态 | **重复 →** §2 冷开场、§8b |
| 同上 | §8.2 收束：兑现后逐拍问加深/转义/重复、不连写同向决定、不用口号；代价不自动复位 | **搬 →** §8 |
| 同上 | §8.3 精确出去状态 | **重复 →** §8 `[连续性]` |
| 同上 | §9 修订十一遍（因果、选择、证据、场景、可表演、具体性、生产事实、声音潜台词、扫读、经济性、所有权） | **搬 →** §9 九遍（选择/证据/死线合成"条件遍"，声音潜台词并入对白遍，所有权并入末尾"列出语义变化"） |
| 同上 | §10 现有剧本最小规范化 | **搬 →** §1b |
| 同上 | §11 合成示例（打印店） | **不搬**：示例角色与 drama-forge 示例重复，方法已在 §3 工作卡 |
| 同上 | §12 失败征兆 | 新增项 **搬 →** §10 失败征兆句 |
| 同上 | §12 审查问题 1–15 | **搬 →** review-checklists §C1–C3、§C7 |
| `references/dialogue-craft.md` | §1 规则分级 | **重复 →** review-checklists §0.2 |
| 同上 | §2 议程表 | **搬 →** §4d |
| 同上 | §3 台词是行动、策略库、商业爽剧用途词、策略受阻 | **重复 →** §4"有用途"与"台词是行动" |
| 同上 | §3.3 方法的反向条件表 | **搬 →** §4d |
| 同上 | §4 潜台词三层、推断依据 | 三层 **搬 →** §4d；推断依据 **重复 →** §4 |
| 同上 | §5 信息进入冲突、说明量由现场认知决定 | **重复 →** §4 |
| 同上 | §6.1–6.2 五个声音维度、声音卡 | 维度 **重复 →** §4 最后一条；声音卡 **搬 →** §4d"人物口吻卡"（写进视觉设定人物条目） |
| 同上 | §6.3 本地化与母语审读 | **重复 →** §4c（drama-forge 原有，更完整）；审读 **重复 →** review-checklists §C4-8 |
| 同上 | §7 权力不是音量、关系动作 | **搬 →** §4d |
| 同上 | §8.1–8.3 动作非填充、停顿有对象、打断的权力 | 停顿 **重复 →** §4；打断 **搬 →** §4d；动作非填充 **重复 →** §4 失败征兆 |
| 同上 | §8.4 长发言用动作断开 + drama-forge 项目例外 | **搬 →** §4d（例外本来就指向 drama-forge §4） |
| 同上 | §9 高密度对白：可见锚点、每轮不同工作、听者行动 | **搬 →** §4d |
| 同上 | §10 修订流程（标注行动、回应关系、删共同已知、策略序列、交换说话人测试、朗读、保护风格） | **搬 →** §9 第 6 遍；保护风格 **搬 →** §9 |
| 同上 | §11 合成示例 | **不搬**：方法已被 §4d 覆盖 |
| 同上 | §12 失败征兆与审查问题 1–9 | 征兆 **重复 →** §10；问题 **搬 →** review-checklists §C4 |
| `references/scene-sound-dramaturgy.md` | 五问、留白、声音不替表演、多人分层、交接边界、失效检查 | **搬 →** §5c；交接边界改指 video-prompts-general §9、edit-and-delivery §5 |
| `references/scene-handoff-capsule.md` | 长单集跨上下文的最小交接摘要（不落盘、以正文为准、写完删除） | **搬 →** §9 末段"长单集分批续写" |
| `references/substitutable-realization.md` | 功能/当前实现/备选实现、备选四判据、删场永不是备选、提前自我阉割与假备选、合成示例、自检 | **搬 →** §7c（例子改成符合"认知要台词或物件说破"的版本）；自检 **搬 →** review-checklists §C7-6 |
| 同上 | "套件不内置平台审核标准、只在创作者标注时生效" | **改写**：drama-forge 全自动，由导演岗对生成风险高的关键拍主动标；不涉及平台审核判断 |
| `scripts/screenplay_index.py` | 字节级块索引、块 ID、修订映射；格式诊断（非法标头、场外内容、未知/未闭合标签、VO/OS 语法、行首冒号歧义、半角冒号、【】方言、注释） | 格式诊断 **搬 →** `scripts/screenplay_lint.py`（SP01–SP08、SP11）；块索引与修订映射 **不搬**：drama-forge 不维护块 ID（与"不建第二套状态"一致） |
| `scripts/duration_estimate.py` | 按项目声明语速估时、VO/OS 计时、注释不计 | **重复 →** `shots_tool.py` G16 与 `common.speech_seconds`；它文档里点名的"注释被当台词、行首冒号被当对白"两个坑，drama-forge 的 `parse_screenplay` 也有（已实测），由 `screenplay_lint.py` SP04/SP08 拦截，根治见下"交总装" |
| `scripts/voice_sheet_check.py` | 配音表逐字投影检查（line_text 必须等于剧本块） | **重复 →** G10（shots.json 台词逐字在剧本里）；配音表本身见下行 |
| `scripts/selftest.py` | 上面三个脚本的自测 | **不搬**原测试；新脚本测试在 `merged_selftest.py::test_screenplay_lint` |
| `scripts/__pycache__/*.pyc` | 编译缓存 | **不搬**：生成物 |
| `assets/beats.jsonl` | 因果节拍记录（含 replaceable_realization 字段） | **不搬**：drama-forge 节拍"不落盘"（screenplay §3 工作卡）；可替代实现改记决策记录（§7c） |
| `assets/episode-card.json` / `episode-card-standalone.json` | 单集契约卡（进入/退出状态、信息释放、节奏计划） | **不搬**：**重复 →** `情绪集纲.md` 一行 + `[连续性]` + scene-state-and-reveal 三本账；另建 JSON 卡与"不建第二套状态"冲突 |
| `assets/screenplay.md` | 剧本模板 | **搬 →** `assets/templates/剧本.md`（改成 drama-forge 口径：情绪标签、读音、`[连续性]` 含下集前 5 秒） |
| `assets/voice-record-sheet.jsonl.md` | 配音上下文字段：对谁说、上一句、此刻知道什么、策略、读音决定、目标秒数；剧本为准 | **不搬到本 lane**（属配音/生产）；`reading`、逐字与剧本为准 **重复 →** production-and-review §10、G10/G44；上下文四字段（addressed_to / preceding_line / speaker_knows_now / tactic）建议总装或生产 lane 并入 production-and-review §10 的"配音表"——见下 |

## short-drama-review

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 审查 Markdown 结构（范围/结论/复核方式/问题块/规则） | **搬 →** review-checklists §0.4 + `assets/templates/审查.md` + `review_md_check.py` |
| 同上 | 审查范围十类 | **改写搬 →** review-checklists 按阶段 A–J + R 组织 |
| 同上 | 工作流：冻结范围、先查可证明事实、带证据审、跨文档综合、结论分派 | **搬 →** §0.1 原则 1–3、§0.4 |
| 同上 | 结论 APPROVE / APPROVE_WITH_NOTES / REVISE / PROVISIONAL | **不搬（冲突）**：drama-forge 用 PASS / REVISE / BLOCKED（SKILL"每次执行"第 3 条）；映射写在 §0.3（PROVISIONAL→BLOCKED） |
| 同上 | 严重程度 blocker/major/minor/note | **搬 →** §0.2 |
| 同上 | 创作者口味检查（台词密度、反应 1 秒、全镜 ASR、画质不作重拍理由） | **重复 →** screenplay §4、G05、production-and-review §5/§7、SKILL 硬约束 6 |
| 同上 | 边界：不提交生产、看不到媒体保持未知、观察有边界、审查只留最小证据 | **搬 →** §0.1 原则 7、9；"不提交生产" **重复 →** SKILL 硬约束 9 |
| 同上 | "修改和复审只有用户明确请求时开始" | **不搬（冲突）**：drama-forge 两轮内自动改与复审（SKILL"每次执行"第 3 条） |
| `agents/openai.yaml` | 显示名 | **不搬** |
| `references/stage-contract.md` | REV-01…REV-11 | REV-01/02/03/04/05/06 **搬 →** §0.1、§0.4、§0.7；REV-07 **改写搬 →** §0.1 原则 6（PASS 不冒充用户认可）；REV-08 **搬 →** §E4 第 9 问、§F–J；REV-09 **搬 →** §0.1 原则 8、§0.6；REV-10/11 **搬 →** §F–J 观察校准（五种处置 **重复 →** production-and-review §6） |
| 同上 | "不建立 JSON/JSONL、来源快照、哈希" | **重复 →** 本 lane 选择：审查只落 Markdown |
| `references/review-method.md` | 机械先于口味、finding 六要素、跨层追踪、复审只看 preserve set、反模板不靠禁词表 | **搬 →** §0.1、§0.4、§0.7；复审 **重复 →** SKILL"writer 对 keep 清单字面比对" |
| `references/anti-template-repair.md` | 诊断四层、过度解释/收口/工整、信息密度均匀、代价即时结清、修订不是换同义词、误报反例、finding 示例 | **搬 →** §0.7（代价即时结清另挂 §B-8） |
| `references/rubric-story-script.md` | Story promise and engine | **搬 →** §A-2 |
| 同上 | Episode shape（主角选择造成结果、只熬到被救的不是主角、只看剧本能否认出赌注、手艺压过题面、结尾形式、不可逆被写回） | **搬 →** §C1 |
| 同上 | 容量估计只作参考、不派配额 | **搬 →** §C6-3 |
| 同上 | 装置契约层 vs 披露层、事后扩权、拿掉装置还剩不剩选择、预知退化、授权能力代价 | **搬 →** §A-5、§A-6（story-engine §4 已有条款要求，**重复**部分不再展开） |
| 同上 | Entry / character / serial memory（入口窗口、人物弧四件、三本账、证据只证明到哪层、连续性标签不能证明未发生、外压与情绪负荷起落） | **搬 →** §B-7、§C5-4、§C7-2；人物弧 **搬 →** §C9 常见 finding |
| 同上 | Scene test | **搬 →** §C2 |
| 同上 | Action and production meaning（生产标签、配角策略、筹码消失的原因、死线、有限单位、时间戳一致、压缩过程、多载体冗余、新发明资源、外人救场、机制看清后台词别再解释） | **搬 →** §C2 末段、§C3、§C7 |
| 同上 | Dialogue | **搬 →** §C4 |
| 同上 | drama-forge 项目例外（单句长度、关键认知说破、母语审读、事件起因、关键物品） | **重复 →** screenplay §4、§4c、§5b；问题 **搬 →** §C3-1、§C4-8/9、§C5-1/2 |
| 同上 | Replaceable realization 审查 | **搬 →** §C7-6 |
| 同上 | Common findings（含虚假悬念、前情回顾、反派缺节制理由） | **搬 →** §C9、§C6-2；"前情回顾一律算错" **不搬（冲突）**：screenplay §8b 允许有叙事必要的短回顾，§C6-2 只问虚假悬念与重复吊 |
| `references/rubric-source-analysis.md` | 原著分析层审查（索引对齐、抽样声明、事实回查、功能提取、人物归并、改编判定与候选集、不属于本表） | **搬 →** review-checklists §R（去掉对 novel_index.py 的命令依赖，改成要答的问题） |
| `references/rubric-assets-prompts.md` | Occurrence 决策；身份 vs 变体（人物/地点/道具）；关系标签不能决定美丑体型肤色 | **搬 →** §D-2、§D-3、§D-4 |
| 同上 | 同地点同时段各视图光向一致（IMG-10） | **搬 →** §D-3 |
| 同上 | Voice direction AST-07…12 | 专名两种写法、相近音色须写区别点、音色描述不混入情绪/混响/底噪 **搬 →** §D-6；"音色只由参考录音承载、文字不能代替" **不搬（冲突）**：drama-forge 的 refs.json `voice` 文字描述要逐字进 H3 提示词（G21） |
| 同上 | Prompt recipe（参考图用途、可照搬/不可照搬、各类图的要求、编辑 delta） | **搬 →** §D-7、§D-8；各类图要求 **重复 →** visual-assets §7–8、G18–G19 |
| 同上 | Prompt quality failures | **搬 →** §D-8 |
| `references/rubric-visual-motion.md` | Coverage and meaning | **搬 →** §E1-2/3 |
| 同上 | Shot purpose and geography（导演方案真不同、场次视觉计划、信息权限与裁切遮挡） | **搬 →** §E2-1、§E2-5、§E2-6；导演方案 **重复 →** storyboard-keyframes §2d |
| 同上 | Frozen keyframe（单一瞬间、起点投影、漏绑第二个人、控制范围、参考槽用途、设定集里根本没有的条目） | **搬 →** §E3 |
| 同上 | Motion（起点、表演、多人各自触发、注意交接、摄影机、环境/声音、终点、选择性变换、分段时间算术、容器算术、轴线、画面左右） | **搬 →** §E4、§E2-5；多镜容器与补拍/替代版记账 **不搬**：drama-forge 一镜一视频任务，重拍开新 take（SKILL 硬约束 8），没有容器与 MOTION 母版关系；配乐相对进出 **重复 →** edit-and-delivery §5（配乐后期另做） |
| 同上 | Cross-shot continuity | **搬 →** §E5-6 |
| 同上 | Common findings | **搬 →** §E6 |
| 同上 | drama-forge 项目例外（一眼看懂、视线、同一人不拆两镜、节奏下限、系统面板） | **重复 →** storyboard-keyframes §2c/§4/§7b/§7c、styles §12；问题 **搬 →** §E1-1、§E2-2/3/4、§E5-7 |
| 同上 | REV-08 生产风险清单（出字、配乐、服装漂移、轴线、口型、分段时长、情绪强度不符） | **搬 →** §E4-9；其余 **重复 →** production-and-review §7 重拍决策表 |
| `references/production-quality-gates.md` | 阻断分级 | **重复 →** §0.2 |
| 同上 | 跨环节返工原因六类（覆盖丢失、表演只有标签、空间状态漂移、文字声音边界、负面补丁淹没动作、版本/执行状态冒充内容） | **搬 →** §E1、§E4、§D-7；版本/状态 **重复 →** quality-contract（哈希绑定、auto 只写 pending） |
| 同上 | 指令优先级六级 | **搬 →** §0.5 |
| 同上 | 改写回归表 | **重复 →** production-and-review §6 六行义务；补充核对项 **搬 →** §0.6 |
| 同上 | 各环节证据问题（剧本、资产、分镜关键帧、视频提示词；尾帧只是终点投影、时长账、遮挡区） | 剧本/资产/关键帧/视频 **搬 →** §C、§D、§E3、§E4；尾帧 **重复 →** storyboard-keyframes §5b；遮挡区与容器对账 **不搬**：drama-forge 无播放面遮挡区声明与多镜容器 |
| 同上 | 缺输入只阻断它支持的判断 | **搬 →** §0.3 |
| 同上 | 生产纪律八条 | **重复 →** production-and-review §1、§6（重试按被拒那项路由）、SKILL 硬约束 2 |
| 同上 | 合格/不合格审查问题示例 | **搬 →** §0.4 |
| `references/project-calibration.md` | 输入参考观察 vs 生成结果观察、观察记录要素、代表性试跑、观察→诊断五步、先定处置、单变量修订、复核边界 | **搬 →** review-checklists §F–J 观察校准；处置五选一 **重复 →** production-and-review §6；试跑 **重复 →** production-and-review §3 金丝雀；升级规则 **重复 →** SKILL"修改纪律"≥3 次 |
| 同上 | "只消费创作者授权的文字观察、本技能不看媒体" | **不搬（冲突）**：drama-forge 由模型直接看图听审（SKILL 硬约束 11） |
| `scripts/review_check.py` | findings/verdict JSON 校验：字段齐全、open fatal/error 必须有 required_change、blocking 数与结论一致 | **改写搬 →** `scripts/review_md_check.py`（校验 Markdown 审查：结论与未关闭 Blocker/Major 一致、Blocker/Major 字段齐全、编号不重复、状态合法、复核方式、keep、模板未填） |
| `scripts/selftest.py` | review_check 自测 | **不搬**原测试；新测试在 `merged_selftest.py::test_review_md_check` |
| `scripts/__pycache__/*.pyc` | 编译缓存 | **不搬** |
| `examples/minimal-findings.jsonl`、`examples/minimal-verdict.json` | JSON 格式示例 | **不搬**：drama-forge 审查只落 Markdown；示例改成 review-checklists §0.4 与 `merged_selftest.py` 内的 Markdown 样例 |
| `assets/finding-template.jsonl`、`assets/verdict-template.json` | JSON 模板（含 disposition 字段） | **改写搬 →** `assets/templates/审查.md`；disposition 概念 **重复 →** production-and-review §6，校准里用（§F–J 第 3 条） |
| `assets/supersession-decision.example.json` | 替代版取代母版的复核记录 | **不搬**：drama-forge 没有母版/替代版关系，重拍开新 take，选哪个 take 由 review.json 记录（quality-contract） |

## 交总装：建议原处改成引用（本 lane 不能改这些文件）

1. `SKILL.md` 阶段表 C 行："reviewer 子代理按 story-engine §11 + screenplay §10 审" → "reviewer 子代理按 [review-checklists.md](../review-checklists.md) §A–C 审"；E 行门列补"reviewer 按 review-checklists §D–E"；C 行"门 / 命令"加 `screenplay_lint.py`。
2. `SKILL.md`"每次执行"第 3 条："按参考里的审查问题引用证据写 `审查/<EP>-审查.md`" → "按 review-checklists.md 写，格式与分级见其 §0；写完跑 `review_md_check.py`"。
3. `SKILL.md`"深挖时读的本地套件"一段：`short-drama-write/references/（script-craft、dialogue-craft）`、`short-drama-review/references/（rubric-story-script、production-quality-gates）` 要删（子 skill 删除后是死链）；改成"剧本手艺见 screenplay §1b–§9，审查见 review-checklists"。
4. `SKILL.md` 安装维护：加 `python3 scripts/merged_selftest.py`（合并进来的新检查的离线自测）。
5. `story-engine.md` §11 问题 1–18：替换成一句"审查问题见 review-checklists §A（立项）、§B（集纲）、§C（剧本）"，失败征兆段和 keep 清单那句可保留（写作者自查用）。**注意**：§11 在本 lane 工作期间被其他 lane 加到了 18 问（15–18 已收进 review-checklists §B-10/11、§A-7、§C5-7）；总装替换前再 diff 一次，有新增先补进 review-checklists。
6. `styles.md` §11 八问 → "见 review-checklists §A-8、§D-5/9、§E5"。
7. `storyboard-keyframes.md` §2c"写完自问（reviewer 同样要答…）"保留写作者自问，括号改成"reviewer 按 review-checklists §E1"；§10"reviewer 核查：…"整段 → "reviewer 按 review-checklists §E"。
8. `visual-assets.md` §4b"空间逻辑检查（写底板提示词前过一遍，reviewer 审视觉设定和分镜时必答）"：表格保留（写作者用），括号改成"reviewer 按 review-checklists §D-1"。
9. `pipeline-contract.md` §7 末段"戏好坏由 reviewer 子代理按 `story-engine.md` 和 `screenplay.md` 的审查问题判" → "按 `review-checklists.md` 判"；§3 阶段表 C 行同理；§1 目录布局加 `项目开发/原稿/<EP>-原稿.*`（现成剧本原稿，screenplay §1b）和 `审查/<EP>-审查.md` 的格式引用；§7 表后可加一句"`screenplay_lint.py`、`review_md_check.py` 是非编号的格式检查"。
10. `production-and-review.md` §3b/§4/§5、`quality-contract.md`、`edit-and-delivery.md` §7：流程留在原处，可在各节首加一句"审查分级与输出格式见 review-checklists §0"（可选）。

## 交总装：发现的问题（不归本 lane 修）

- **`scripts/common.py::parse_screenplay` 误读对白（已实测）**：`<!-- 待确认：…… -->` 被读成说话人 `<!-- 待确认` 的对白；`他写下两个字：军宣。`、`第二格：一只手……` 被读成对白；第一个场次标头之前的正文被静默丢弃。后果是 G11 误报"对白没有镜头承载"、G37 误报句长、说话人清单被污染（G15 因为从剧本本身取说话人而放过）。建议：跳过 `<!-- -->` 块；视觉设定存在时只把人物条目里的名字认作说话人，其余冒号行当动作。修之前由 `screenplay_lint.py` SP03/SP04/SP08 拦截。
- `assets/example/EP001/剧本.md` 的 4 句台词都没有情绪标签（`screenplay_lint` SP09），和 screenplay §4b"每句都带"不一致，建议补上（示例会被照抄）。
- `assets/templates/情绪集纲.md` 首段"创作者通过后再写剧本"与全自动模式冲突，建议改成"reviewer 审过后再写剧本"。
- screenplay §2 写"成片严格按时间顺序"，SKILL 6b 写"闪回、闪前可以使用，但必须标清"；本 lane 按任务给的硬规则"时间顺序不闪回"处理规范化（§1b 第 4 条默认改顺叙，确需保留才按 6b 标清），没有改 §2 原句。两处口径需要总装统一。
- 配音表上下文字段（对谁说、上一句是谁说的、说话人此刻知道什么、这句的策略）对"配音平、语气不对"有直接帮助，建议生产/配音 lane 并入 production-and-review §10 的配音表。

## 事故记录：`scripts/merged_selftest.py` 被本 lane 误覆盖，已恢复

本 lane 用 Write 新建 `merged_selftest.py` 时，文件其实已被剪辑/总控 lane（`test_hub_tool`）和生产通道 lane（`test_video_produce_providers`）建好，被整份覆盖（11:38:09）。视觉 lane 随后已在新文件上补回 `test_visual_lint`。恢复方法：从会话记录里按时间顺序重放那两个 lane 对该文件的全部写操作，再用覆盖前留下的 `__pycache__/merged_selftest.cpython-313.pyc`（源文件 11:37:40、21758 字节）逐函数比对字节码——`require`、`_raises_exit`、`test_hub_tool`、`test_video_produce_providers`、`main` 全部一致。现在文件里是 5 个 test_*（hub_tool、video_produce_providers、visual_lint、screenplay_lint、review_md_check），`python3 scripts/merged_selftest.py` 5/5 通过。另外顺手让 `main` 同时接受 `merged_selftest.py NAME` 和 `-k NAME`：`references/providers.md` 写的是 `-k providers`，原来的 `main` 会把 `-k` 当过滤词、一个测试都不跑还返回成功。

## 拿不准的取舍

1. **结论 BLOCKED 的含义**：drama-forge 原文只列了 PASS/REVISE/BLOCKED 三个词没有定义。本 lane 定为"有未关闭 Blocker（含缺关键输入）"，并让"两轮没过的未决 Major"不计入未关闭（对应 pipeline-contract §8"按修订建议直接改、记未决、不停"）。若总装希望 BLOCKED 只表示"缺输入"，改 review-checklists §0.3 和 `review_md_check.py` 的 RV06 即可。
2. **秒表核对判 Major 只在 commercial_fast 下**（§C6-1）：screenplay §2 已写明秒表是 commercial_fast 的节奏参考、非硬门，所以 general 模式记 Note；而原 screenplay §10 没有这个限定。
3. **§R 原著改编分析**放进了审查清单，但 drama-forge 目前没有原著分析阶段；是否保留取决于小说分析 lane 是否把那个阶段并进来。
4. **可替代实现（§7c）**原套件只在创作者标注时启用，本 lane 改成导演岗对生成风险高的关键拍主动标一行；这是为了适配全自动，但会给导演岗增加一点工作量。
5. `screenplay_lint.py` 的 SP12 镜头术语是关键词匹配（特写、近景、机位、运镜……），会有少量误报；只作 warn。

## 总装补记（2026-09-26）

"建议原处改成引用"1–9 已执行：SKILL.md 阶段表 C/E 行与"每次执行"第 3 条、安装维护；story-engine §11、styles §11（第 9、10 问先补进 review-checklists §E5 第 8、9 条）、storyboard-keyframes §2c/§10（§10 里未覆盖的"删掉或合并本镜""站立看见移动""提示词互相冲突或无用限制"先补进 §E2-8、§E4-10）、visual-assets §4b、pipeline-contract §1/§3/§7。第 10 条（生产阶段各文件节首加引用）未做：这些节是操作步骤，不是问题清单，review-checklists §F–J 已反向索引。`common.py::parse_screenplay` 误读与示例剧本缺情绪标签两条未修，留给后续（改示例会牵动 selftest 的逐字对账）。
