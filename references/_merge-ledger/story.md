# 合并台账：剧情与开发 lane

- 来源：`short-drama-develop/` 全部（36 个文件）、`short-drama-novel-analyze/` 全部（11 个文件），2026-09-26 读取的当前版本（其中 develop 的 genre-cards.md、premise-devices.md、commercial-payoff-craft.md、assets/creative-brief.md 在工作区有别的会话未提交的改动，按改动后的内容读）。
- 本 lane 写入的 drama-forge 文件：
  - 修改 `references/story-engine.md`、`references/premise-novelty.md`、`assets/templates/情绪集纲.md`
  - 新建 `references/series-long-form.md`、`references/adaptation.md`、`references/genre-cards/`（`索引.md` + 12 张卡）、`assets/templates/改编契约.md`、`assets/templates/跨集记忆.md`
- 通用改写口径：原套件"每一步请创作者确认 / 接受 / 停靠"的交互流程，统一改成 drama-forge 的自动决策 + 决策记录；付费授权和模型选择不在本 lane 范围内，仍按 SKILL.md 硬约束 1、1b 由用户定。原套件的 `structural_invariant / reviewed_invariant / craft_default / taste_option` 四级分类不搬（drama-forge 用机械门 G 号 + reviewer 审查问题 + 决策记录豁免来表达同一件事），各条规则按内容落到对应位置。所有"见 short-drama-xxx"的链接都没有保留；新文件末尾只以文字注明合并来源。

## short-drama-develop

| 来源文件 | 独有内容要点 | 去向 |
|---|---|---|
| `SKILL.md` | 五种入口判断（只有点子 / 有长材料 / 只要分集 / 已有单集剧本 / 多集整稿）；锁定创作者契约（不可改、可探索、形式约束、反复回报）；方向候选须改变机制；导演阐述只出候选；产物清单；规则四级 | 入口判断 → story-engine §10"入口判断"；锁定契约 → adaptation §6.1 与 premise-novelty §6（用户点子算候选）；"候选须机制不同" → 已有（premise-novelty §6 第 2 步）；未选方案不进既定事实 → story-engine §10、premise-novelty §6 第 6 条；产物清单（creative-brief、story-engine、director-brief、adaptation-map、series-arc、episode-intake-index、episode-map）→ 不搬：drama-forge 的对应产物是系列简报、情绪集纲、改编契约、改编对照、跨集记忆（pipeline-contract §1 + 本 lane 新模板）；"创作者接受后才作下游来源"→ 改为自审 + 决策记录；规则四级 → 不搬（见上） |
| `agents/openai.yaml` | 子 skill 在 Codex 界面的显示名和默认提示 | 不搬：界面元数据，drama-forge 已有自己的 `agents/openai.yaml` |
| `assets/adaptation-map.example.jsonl` | 改编映射记录的字段：source_span、function_summary、mentioned_entities（unresolved）、disposition、new_carrier、preserved / lost、creator_acceptance | adaptation §6.6 功能对照表（字段改成中文口径，`creator_acceptance` 改为 `status`） |
| `assets/creative-brief.md` | 不可改来源事实逐条落集或延后；创作者契约（体验、不要变成什么、主题张力、尺度、结局、边界）；形式与制作边界；戏剧承诺六要素；方向候选的机制差异字段（退出成本、终止条件、制作负担、擅长 / 牺牲）；人物驱动力；叙事切入窗口与前史储备表；接受记录 | 大部分重复已有：系列简报模板已有一句话、四问、形态、人物、禁止项、视觉方向。独有部分：不可改事实落集 → `改编契约.md`"不可改承诺"表 + story-engine §8"登记不等于兑现"；机制差异字段 → premise-novelty §6 第 4 步"前三名补一张机制差异表"；退出成本 / 终止条件 / 主题张力 → story-engine §2 六部件与主题；驱动力 + 前史 + 切入 → series-long-form §1–2；接受记录 → 不搬（决策记录替代）。系列简报模板本身未改（别的会话有未提交改动，且模板列被 project_tool 解析），见"拿不准"第 4 条 |
| `assets/emotion-episode-outline.md` | 情绪集纲模板 | 重复已有：与 drama-forge `assets/templates/情绪集纲.md` 基本一致。顺手把 drama-forge 模板里"创作者通过后再写剧本"改为"自审通过后再写剧本（不等人确认，取舍记决策记录）"，把与 episode-map 字段的对照改成与 series-long-form §8 分集卡字段的对照 |
| `assets/episode-map.jsonl` | 单集契约 JSONL 字段：incoming_state、hook、objective、opposition、turn、local_dramatic_result、information_release（含 visible_carrier / supported_claim / unresolved_inference）、premise_device_disclosure、outgoing_pressure、handoff_state、setup_ids / payoff_ids | series-long-form §8"完整分集卡（可选）"，字段改成中文、只在关键集用；信息释放三层 → story-engine §8 证据结论边界；装置披露 → series-long-form §5 第 6 项与分集卡。JSONL 格式不搬（drama-forge 的集纲是 Markdown，不维护两份） |
| `assets/story-engine.md` | 故事引擎模板：引擎回路、退出理由、可升级状态表、装置契约表（DEV 条款 + 可靠性列）、人物行动模型与跨集进展表、关系压力网、信息与证据表、铺垫与兑现义务表、跨集记忆最小集、主题进入选择、视觉声音方向、引擎终止与变形、分集交接原则 | drama-forge 的系列简报承担故事引擎的角色，大部分重复已有（装置条款表、人物、视觉方向）。独有部分：可靠性列 → story-engine §4"不可靠宣告写进条款可靠性一栏"（系列简报模板已有可靠性列）；跨集进展表、跨集记忆、铺垫表 → `跨集记忆.md` 模板 + series-long-form §3、§5；铺垫台账格式 → story-engine §8；终止与变形 → story-engine §2 终止条件；"绝不能无原因重置的事实" → series-long-form §5 + `跨集记忆.md` §8 |
| `references/adaptation-craft.md` | 改编契约四类；长材料先建语义层、原文不进开发文件；功能账本；先删线再合并（五条判据、慢线陷阱）；合并人物五问与合并场景条件；信息视觉化阶梯；因果桥；改编功能对应表；单集化；登记不等于兑现（STY-23）；回原文用事件锚点、知情状态比对、召回只补细节（STY-22） | adaptation §6.1–6.7、§7；登记不等于兑现 → story-engine §8。视觉化阶梯第 5 级"VO/OS/主观画面"改写为：先用台词明说规则（SKILL.md 6c），`[VO]/[OS]` 放最后并提醒 H3 不生成画外人声（硬约束 11）；"保留旁白、倒叙是创作者选择"与 drama-forge 顺叙规则冲突，不搬为默认，改为 adaptation §9 对应表（倒叙改顺叙，确需闪回按 6b 标清） |
| `references/commercial-payoff-craft.md` | 四问、主爽点类型、两种不爽、情绪步骤表、兑现三件事（STY-26）、情绪集纲六件事（STY-25）、台词按用途、分镜先排信息、先用分镜图和临时配音剪一版、四种发行模式、合成例、外部案例表与"研究对标剧记录前后情绪"、饱和设定与市场摘要 | 四问、主类型、情绪步骤、兑现三件事、集纲六件事、合成例、失败征兆 → 重复已有（story-engine §1、§5、§6、§11；市场摘要与饱和设定原本就是 market-hits / premise-novelty 的摘要）。独有并已搬：两种不爽与受气段检查 → story-engine §3；承制买断、品牌文旅、出海 → story-engine §5 发行模式；IAP 门槛集写法 → story-engine §5（原文件指向子 skill 的链接已删）；"研究对标剧记录这一句之前压了什么情绪" → adaptation §8。台词按用途 → 重复已有（screenplay §4）；分镜先排信息 → 重复已有（story-engine §4"观众先于反派看见底牌"、storyboard-keyframes）；先剪分镜图版 → 重复已有（G2 静帧预演）。外部案例表（斩仙台、兴安岭诡事、Zephyr、ReelShort）→ 不搬：原文自己声明"不进交付物、不作质量判据"，市场判断以 market-hits 为准（斩仙台已在 market-hits §1.2） |
| `references/creative-reference-intake.md` | 对标材料声明职责（主参考 / 补充 / 无关不加载）；从观察写到机制的 YAML 卡；must_not_copy；下游只读去引用候选；迁移检验与替代机制比较；参考不是质量证明 | adaptation §8（YAML 改中文字段；"由创作者选择"改为按分数自选并记决策） |
| `references/director-brief-craft.md` | 导演阐述：基础写法、可验收约束型（空间、身份与状态、连续性、对白与接收、结尾）、单集导演阐述、风格速记、按已知制作能力写表演、跨集阶段的镜头语言职责、反模式、拆分参数 | 大部分重复已有，归视觉 / 分镜侧：风格锁定与视频头句 → styles.md §1；身份与造型变体 → visual-assets；相邻镜连续性 → storyboard-keyframes 与 G26；按实测能力写规则、不从别的项目移植 → SKILL.md"模型行为先记账再立规矩"与 `模型观察.md`；反模式"空泛形容词无法验收" → styles.md Look Development。独有的"跨集阶段 + 镜头语言职责 + 节奏目的"→ series-long-form §4.2 双轨节奏与 §6 季规划吸收了其叙事部分；镜头语言部分不搬（属分镜 lane，且 drama-forge 的节奏下限与长镜头合并规则已定镜头节奏）。`production_profile / creator_authority` 写入流程 → 不搬（short-drama.json 专属，drama-forge 用 drama.json） |
| `references/episode-design.md` | 分集工作定义；单集契约字段；可选"结果预演"开场；钩子六类与出去压力五问；IAP 门槛集；节拍字段与"所以 / 但是"朗读；重复与升级六问；场景化前可见性检查；转折写成动作不是功能（STY-24）；系列弧线四功能；分集地图列；长线与单集双重责任；集间交接逐项核对；扩写、压缩、重排的判据；容量可行性预算（STY-16）；只写本集独有的事 | 转折写成动作、"所以 / 但是"、只写本集独有、容量估算、门槛集 → story-engine §5；单集契约字段、分集地图列 → series-long-form §8；集间交接逐项核对、知识关系伤势无原因跳变 → series-long-form §7 第 2 步；系列弧线四功能（旧策略可用 → 被反制 → 成本显形 → 引擎变形）→ story-engine §2 终止条件与 §9 耗尽处置已覆盖，不另列；钩子六类 → 重复已有（story-engine §5 六型 + genre-cards/索引"钩子从本集结果往下长"）；扩写压缩重排判据 → 重复已有（screenplay §9 修订纪律、story-engine §9 耗尽）。"结果预演（先给未来结果再回到决定）"→ 不搬：与 drama-forge 顺叙默认冲突，SKILL.md 6b 已规定闪前须标清 |
| `references/genre-and-hook-playbook.md` | 六轴题材比较、跨题材推进表（压力、先给什么结果、必须拍清什么、常见问题）、各题材因果链、开场入口比较、钩子接着本集结果、制作难点清单、审查问题 | genre-cards/索引.md（跨题材比较表、开场入口、钩子表、制作难点清单）；各题材因果链并入对应题材卡；"二维漫剧可用 hold pose 与留白"→ 生活流卡改写为"余韵靠环境声与停留，但不低于节奏下限"；"不规定第几秒"与 drama-forge 单集秒表冲突处 → 以 screenplay §2 与 premise-novelty B1 为准，不搬"不规定"的表述；家庭戏"预示未来结果再回到选择"→ 不搬（顺叙） |
| `references/genre-cards.md` | 召回规则（只读一张、跨题材主卡全读辅卡摘一两条、传给下游的只保留相关条目、卡名不进交付物）；冲突优先级；卡一览与置信度；装置不当题材查表；不要把卡写成硬规则 | genre-cards/索引.md（优先级改成：用户硬约束 → drama-forge 硬约束与已定系列简报 → 题材卡 → 手感；"不要写成硬规则"与 story-engine §5 相邻集钩子不同型的门冲突处，注明那条门照旧有效） |
| `references/genre-cards/复仇打脸.md` | 题材核心、压力与发动机三件事、策略与三层信息权限、兑现落点、场面颗粒、钩子、前中后期、制作难点、禁止漂移 | genre-cards/复仇打脸.md（加兑现子模式与 L 层级对应、市场对标、饱和设定提醒；"闪回会新增旧场景"改为"用当下物件，原话奉还不插回放"；公开场合改为半公开小场 + 具名单人反应镜） |
| `references/genre-cards/古装权谋.md` | 同上结构 | genre-cards/古装权谋.md（加穿越种田科举的市场对标与画风；群戏改为具名单人镜 + 接触同框；文书字后期叠加） |
| `references/genre-cards/悬疑规则.md` | 同上结构 | genre-cards/悬疑规则.md（规则纸条可读 → 后期叠加；加悬疑色调、太暗翻车、证据结论边界、规则改写等于规则通胀） |
| `references/genre-cards/家庭关系.md` | 同上结构 | genre-cards/家庭关系.md（加饭桌多人场的视线与接触镜写法、抖音快手市场对标、心声叠加提醒） |
| `references/genre-cards/亲子隐秘.md` | 同上结构，含儿童演员工时限制 | genre-cards/亲子隐秘.md（儿童工时限制改写为 AI 下的"表演可信度 + 萌宝表情口型难拍 + 比例真实"；加团宠靠山长青、相认方式每次换；未成年尺度与真人素材条款保留） |
| `references/genre-cards/职场喜剧.md` | 同上结构 | genre-cards/职场喜剧.md（屏幕内容照抄 → 后期叠加、屏幕背对或只拍手、关键数字台词念出） |
| `references/genre-cards/身份错位.md` | 同上结构 | genre-cards/身份错位.md（加两套身份图的 refs 登记、灵魂互换音色跟谁走、辈分错位市场对标） |
| `references/genre-cards/生活流.md` | 同上结构 | genre-cards/生活流.md（"承接余韵见对应形态卡"改为环境动态与停留、不低于节奏下限；加小本生意与赶山赶海市场对标；商业目标下每集仍有小兑现） |
| `references/genre-cards/仙侠修真.md` | 同上结构（中置信） | genre-cards/仙侠修真.md：按任务要求结合 market-hits §4 修仙专节（升级线节拍、打脸梯、长篇三要素、钩子三类、禁区、3D 优于 2D、续季打法、好拍难拍）与 premise-novelty §8；数字只摘要并注明以 market-hits 为准 |
| `references/genre-cards/豪门婚恋.md` | 同上结构 | genre-cards/豪门婚恋.md（加契约 / 假关系市场对标、霸总傻白甜与"三件套"饱和提醒、亲密动作算接触同框镜） |
| `references/genre-cards/破镜重圆.md` | 同上结构，含四种误会分支与闪回成本 | genre-cards/破镜重圆.md（闪回改为默认不用、确需按 6b 标清并定死时空数；四种分支完整保留；注明榜单无直接数据） |
| `references/genre-cards/动作任务.md` | 同上结构 | genre-cards/动作任务.md（一镜一个起止状态对齐 screenplay §5 与硬约束 6 的关键动作秒数核对；市场对标改为末世囤货 / 资源经营） |
| `references/mechanism-loop.md` | 循环是引擎与分集之间那一层；第一次运行完整演示；循环嵌套、外层赌注更早；一次运行记五项含成本；打乱顺序测试；换向量不换靶心、换承担者；耗尽症状与"对手变笨"根因；没有去处的循环必耗尽；三种处置与并接；换代丢掉的紧迫性三样与"什么都不做会怎样"；把下一个循环埋进来与换代缓冲；落差型循环；与单集契约的关系；合成例 | 已有部分：第一次完整演示、改变五项、耗尽症状、三种处置、禁止并接、去处具体可核对、换向量（story-engine §9 原文）。新搬：运行五项含成本、嵌套与外层赌注、换承担者判据、紧迫性交接与检查问题、埋下一个循环、换代缓冲（注明在爽剧里缓冲不能占满一集）、落差型循环、排班合成例 → story-engine §9；季作为大循环 → series-long-form §6。"不要求每集一次运行"与 drama-forge"每集一次可核对兑现"不冲突（兑现 ≠ 一次完整运行），未另写 |
| `references/multi-episode-intake.md` | 多集整稿接入：原文字节不归一化、只读当前切片、工具只做索引校验切片合并、批大小由 Agent 按实测长度定、手工边界 JSONL、unmapped_spans 只标出前言（集间说明会被并进前一集，要读每集首尾）、merge 不直接覆盖、以地图为唯一完成真相续跑 | adaptation §5.1–5.3；§5.4 新增"规范化进 drama-forge"（格式化成 `EPxxx/剧本.md`、反推集纲、原稿台词保留规则）。`project_tool.py publish` 的发布生命周期 → 不搬（short-drama core 专属） |
| `references/premise-devices.md` | 装置不是题材；四种共同失效；契约与披露两层；条款级闸门与困境驱动的规则通胀判据；先知型的四种信息切法、起点、观众信息权限三档、合成例；授权型的宣告即披露、数值一经披露就被记住、宁可少披露、不可靠宣告、代价可见、装置不替主角做决定、载体与可读文字义务、合成例；饱和设定与生成法摘要；与既有机制接口；自检 | story-engine §4 全部新增段落（装置不是题材、四种失效、实质判据、先知型、授权型、两个合成例）。可读文字义务按 drama-forge"画面不出字"改写：条款用台词或 `[OS]`，数值走后期面板，不逐字重复。饱和设定与生成法摘要 → 重复已有（原本就是 premise-novelty 的摘要）；接口表 → 不搬（指向的是 short-drama 的资产与剧本标签体系，drama-forge 对应物已在各自 references） |
| `references/reveal-reversal-payoff.md` | 承诺重心 × 压力来源 × 回报表；四种动作区分；公平揭示五问与合成例；有因果的反转句式（STY-09）与常见可用反转；回报先于下一股压力；避免机械轮换 | 承诺重心表 → story-engine §3；四种动作、公平揭示、反转句式、常见反转 → story-engine §8"揭示与反转"；回报先于压力 → 重复已有（story-engine §5 爽点间隔门、§6）；避免机械轮换 → 重复已有（story-engine §6 子模式轮换、§9 换向量） |
| `references/serial-character-and-memory.md` | 前史储备（三种去向标签）与叙事切入窗口五问（STY-11）；驱动力七层与关系相撞六句；压力测试与六种弧线结果（STY-12）；每集局部结果须追溯到焦点人物选择（STY-13）与"外力送达"反例；信息权限表与证据结论边界（STY-15）；铺垫是债；双轨节奏（STY-14）；可恢复的跨集记忆六项与更新原则；合成例 | series-long-form §1–5（前史释放按顺叙规则改写：用当下物件 / 台词 / 字幕，不插回忆；双轨节奏的"低 / 低"注明在 IAA 下只能是一两场、不低于节奏下限）；局部结果追溯到选择 → story-engine §5；证据结论边界、铺垫台账 → story-engine §8；跨集记忆 → series-long-form §5 + `跨集记忆.md` 模板（加了第 7 项"装置披露进度"） |
| `references/stage-contract.md` | 独立运行与项目集成；所有权边界；制作形态需要回答的三件事（叙事职责、运动预算、未决试验）；STY-01…STY-26 规则表 | 独立运行 / publish 生命周期 / 所有权 → 不搬（short-drama.json 专属，drama-forge 用 pipeline-contract 与剧组分工）。形态三问 → 重复已有：styles.md §1 与 §1b Look Development（各试一镜）承担形态选择与未决试验，可生成性预算（story-engine §1）承担运动预算。规则逐条：STY-01/02/03 → story-engine §2–3；STY-04/13 → story-engine §5；STY-05 → story-engine §8 铺垫台账（drama-forge 无对应机械校验器，改为 reviewer 问题 16）；STY-06 taste → genre-cards/索引"卡里的钩子取向是可选项"；STY-07 → adaptation §6.3；STY-08 → adaptation §6.4；STY-09 → story-engine §8；STY-10 → 重复已有（premise-novelty B1、screenplay §2）；STY-11/12/14 → series-long-form §1、§3、§4.2；STY-15 → story-engine §8；STY-16 → story-engine §5 容量估算；STY-17 → story-engine §4；STY-18/19 → adaptation §5；STY-20/21 → story-engine §9；STY-22 → adaptation §7；STY-23 → story-engine §8 + 改编契约模板；STY-24 → story-engine §5；STY-25/26 → 重复已有（story-engine §1、§3、§5、§6） |
| `references/story-craft.md` | 五问到戏剧承诺；回报落点（关系 / 地位）；回报先有舞台再有能力；承诺压力测试；引擎一轮回路与六部件；变化空间七维；行动模型八项与"可跟随四问"；关系双向压力；升级四种运动；转折不必是秘密；信息四问；铺垫是义务；主题进入选择；机制差异表；从引擎走向分集的准备问题；共享厨房合成例；失败征兆与审查问题 | 已有：五问 / 一句话承诺、落点、一轮回路、行动模型八项、可跟随四问、关系双向压力、信息四问（story-engine §1–3、§7–8）。新搬：回报先有舞台 → story-engine §1；压力测试补"回报同形"与独特矛盾、六部件（退出成本、终止条件）、主题进入选择 → story-engine §2；升级四运动与"转折不必是秘密"→ story-engine §3；铺垫义务 → story-engine §8；机制差异表 → premise-novelty §6 第 4 步；准备问题 → story-engine §11 问题 18。共享厨房合成例 → 不搬（story-engine 已有职场抢功合成例，series-long-form 用了调度员合成例，再加一个是重复） |
| `scripts/episode_intake.py` | 多集整稿的精确字节索引、手工边界、verify、slice、progress、merge（纯标准库） | 方法写进 adaptation §5.2–5.3；脚本本身未迁（本 lane 无权写 `drama-forge/scripts/`），见"拿不准"第 1 条 |
| `scripts/selftest.py` | episode_intake 的 5 项离线自测 | 同上；若迁脚本需改名（drama-forge 已有 `scripts/selftest.py`） |
| `scripts/__pycache__/episode_intake.cpython-313.pyc` | 编译缓存 | 不搬：可再生的缓存 |

## short-drama-novel-analyze

| 来源文件 | 独有内容要点 | 去向 |
|---|---|---|
| `SKILL.md` | 材料前提（合法持有、只读转化、黑暗元素照常提取、单段失败跳过）；四种入口；S0–S5 管道与停靠；索引是唯一切片真源及四类索引问题、编号单位、长标题行；S1 抽样快评与停靠；`_work/` 与发布；子代理写工作区、主线程发布；S2 并发与覆盖率闸门；S3 不回读原文；S4 归并是候选不是资产；S5 改编价值与回填快评；交接；不写 adaptation-map | adaptation §0–§4（管道改为 A0 阶段；目录改为 `项目开发/原著分析/` 中文文件名，逐章文件名保留 `ch-<N>-extract.md` 以兼容原脚本的覆盖率检查）。S1"停下问创作者是否继续"→ 改为 adaptation §4.2"自动决定拆多少"并记决策；"只有书名"→ 不凭记忆，记决策并在汇报里请用户提供原文，不阻断其他授权工作。`project_tool.py publish` 与 artifact-id → 不搬（short-drama core 专属），改为"子代理写 `_work/`，主线程自检后移到正式路径" |
| `agents/openai.yaml` | 界面显示名与默认提示 | 不搬：界面元数据 |
| `assets/episode-candidate.example.jsonl` | 分集候选字段：story_units、chapter_range、screen_judgement、trope_tags、entering_knowledge、promise_paid、exit_pressure、inherited_facts、preserved_functions、carrier_change、production_load、unresolved、creator_acceptance；sources 头记录 | adaptation §4.6 的 JSONL 合成例（字段保留英文键便于脚本处理，判定值与状态改中文；`creator_acceptance` → `status`；`production_load` 增加 `speaking_roles` 对齐可生成性预算；sources 头记录不搬，来源写在改编契约"来源"节） |
| `references/adaptation-triage.md` | 快评是可推翻的假设；脚本等距抽样、首尾必取、正文极少顺延；六件事；开篇替换点三条；首行覆盖率与三条限定；停靠与"一次跑完"例外 | adaptation §4.2（开篇替换点另要求过 premise-novelty B1 与 market-hits §6；制作负担对照可生成性预算；停靠改为自动决定） |
| `references/adaptation-value.md` | 判定对象是单元；三类判定与 prose_only 典型；不把 prose_only 偷换成 needs_carrier；载体替换四项与"不需要旁白"检验；制作负担作排序依据；桥段标签种子表；分集候选四问与"集数不由本技能定"；回填快评（三类比例不换算只对方向）；交接五条自检与摘要 | adaptation §4.6（三类判定改中文名"能直接拍 / 要换载体 / 只能靠文字"；新载体须符合一镜一人加接触同框、画面不出字、可生成性预算；桥段标签对照 premise-novelty 饱和设定；交接摘要写进决策记录） |
| `references/aggregation-and-entities.md` | 聚合不回读原文；五种故事框架与切法；单元六项与进出状态对接；粒度四条；三条阈值与算法（归属不等于落在范围内）；小体量例外；散落兜底五步；节奏与情绪三件事；人物归并一人一实体、五类称谓与"去掉头衔剩不剩姓名"；设定归纳规则 | adaptation §4.4、§4.5（框架表的升级流加"阶段边界也是季边界"指向 series-long-form §6；设定归纳后的能力规则要改写成 story-engine §4 的 DEV 条款） |
| `references/chapter-extraction.md` | 每章五节固定格式；情节点四段行格式、七种类型、功能字段唯一性；密度 150–200 字；白描与叙事框架词对照表；内心独白写法；硬事实可回溯与相邻实体不挪用；载体记录四列与通道决定下游判定；五条 grep 机械自检及阈值理由；并发批 5–8 章与授权前缀；失败重试与跳过必须传递 | adaptation §4.3（自检命令路径改为 `项目开发/原著分析/章节/`；授权前缀 → adaptation §1） |
| `references/stage-contract.md` | 独立运行与发布生命周期；所有权（不写 adaptation-map、不建资产）；分析层与决策层分开的理由；材料授权；NVA-01…NVA-12 | 发布生命周期 → 不搬（同上）；所有权与"分析层 / 决策层分开" → adaptation 开头两条总原则与 §0；材料授权 → adaptation §1。规则逐条：NVA-01 → §4.1；NVA-02/04/07 → §1 与 §4.3（行号定位、去引用、硬事实回溯）；NVA-03 → §4.3 覆盖率闸门与跳过传递；NVA-05 → §4.2 首行覆盖率；NVA-06 → §4.3 功能写法；NVA-08 → §4.5；NVA-09 → §4.6；NVA-10 → §4.6 分集候选；NVA-11 → §4.2（停靠改自动）；NVA-12 → adaptation §6 由主会话按规则拍板并记决策 |
| `scripts/novel_index.py` | 章节索引 index / verify / sample / coverage（纯标准库；识别中文数字含千两、只认一种编号单位、剔除目录块、按卷校验） | 方法与检查项写进 adaptation §4.1，并给了无脚本时的手工办法（行号 + sha256）；脚本本身未迁，见"拿不准"第 1 条 |
| `scripts/selftest.py` | novel_index 的 5 项离线自测 | 同上；若迁需改名 |
| `scripts/__pycache__/novel_index.cpython-313.pyc` | 编译缓存 | 不搬：可再生的缓存 |

## 与 drama-forge 现行硬规则冲突而没有照搬的内容（汇总）

| 冲突内容 | 来源 | drama-forge 规则 | 处理 |
|---|---|---|---|
| 结果预演开场、倒叙、家庭戏"预示未来结果再回到选择"、改编中"保留倒叙是创作者选择" | episode-design §3.2、genre-and-hook-playbook、adaptation-craft §6 | 时间顺序、SKILL.md 6b 闪回闪前须标清、`cut_order` 服从剧本 | 不作默认；adaptation §9 对应表改顺叙，确需时按 6b |
| 前史、前世信息用回忆或闪回交代 | serial-character-and-memory、premise-devices | 同上；story-engine §6 原话奉还不插回放 | series-long-form §1.1、story-engine §4 改为当下物件、台词、字幕交代 |
| 屏显面板、规则纸条、屏幕内容作为画面上的可读文字 | premise-devices 载体节、各题材卡 | 生成画面不出字（硬约束 4） | 一律后期叠加或台词念出 |
| VO / OS / 主观画面作为信息载体 | adaptation-craft §3 第 5 级 | 能力规则要说出来（6c）；H3 不生成画外人声（硬约束 11） | 放到阶梯最后，注明另做音源 |
| 公开场合群演、大殿群像、群体同框反应 | 各题材卡制作难点 | 一镜一人 + 接触同框（硬约束 3、可生成性预算） | 半公开小场 + 具名个体单人反应镜 |
| "不规定第几秒""开场可以安静" | genre-and-hook-playbook 开场选择、serial-character-and-memory §2.2 | 开场服从故事但要过 B1 前 3 秒钩子与单集秒表 | 保留"从旧办法开始付代价处切入"的方法，同时要求过 B1 与 screenplay §2 |
| 二维漫剧用 hold pose、留白、慢节奏承接余韵 | genre-and-hook-playbook 生活流 | 节奏下限（6f、storyboard-keyframes §7c） | 生活流卡改为环境声与停留，但不低于节奏下限 |
| 每一步等创作者接受、S1 停靠问是否继续、导演阐述由创作者提升 | 两个 SKILL.md、各 references | 全自动 + 决策记录（硬约束 1） | 改为自动决策；付费与模型选择不涉及本 lane |
| 外部案例的播放量、成本 | commercial-payoff-craft §12 | 市场判断以 market-hits 为准 | 不搬 |

## 其他文件里的残留指向（不在本 lane 可写范围，需主会话处理）

- `SKILL.md`"深挖时读的本地套件"一节列出 `short-drama-develop/references/`（story-craft、episode-design、mechanism-loop、premise-devices、commercial-payoff-craft、genre-cards）：子 skill 删除后失效，建议改指向 story-engine、series-long-form、adaptation、genre-cards/。
- `SKILL.md` 阶段表 A 行"读"一栏可补 `genre-cards/`、改编项目加 `adaptation.md`（A0）、长篇加 `series-long-form.md`。
- `references/market-hits.md` 文首"short-drama 套件引用的市场结论……是本文摘要"和 §9 第 7 步"rsync 到 short-drama-develop 并检查摘要"：子 skill 删除后应删掉这两处。
- `references/pipeline-contract.md` §1 目录布局可补改编项目才有的 `输入/`、`项目开发/原著分析/`、`项目开发/改编契约.md`、`项目开发/跨集记忆.md`。

## 拿不准的取舍

1. **两支脚本是否迁入 `drama-forge/scripts/`**：`novel_index.py`、`episode_intake.py` 只用标准库、各带 5 项离线自测，对长书和多集原稿的切片一致性有实际价值。本 lane 无权写 scripts/，adaptation.md 写成"有脚本就用，没有就按手工办法（行号 + sha256）"。建议主会话迁入，自测文件改名（例如 `novel_selftest.py`、`intake_selftest.py`），避免和现有 `selftest.py` 冲突。
2. **长书的拆解范围**（adaptation §4.2）：原套件是"快评后停下问创作者"。我改成默认全量拆，书很长而只授权一季时拆到本季所需单元 + 1 个单元余量，标了 [推断]。
3. **多集原稿的台词是否本地化改写**（adaptation §5.4）：同语言时保留用户原稿台词，母语审读意见只写审查不自动改；语言不同才按 screenplay §4c 改写。这在"台词本地化"硬规则和"用户原稿是契约"之间取了用户原稿优先。
4. **系列简报模板没改**：机制差异表写在 premise-novelty 正文里要求"写在候选表下面"，没有给 `系列简报.md` 加列或加节（该模板有别的会话未提交的改动，且 `## 立项候选` 表被 project_tool 解析）；续季的 `## 季规划`、不可重置事实清单、铺垫台账也只在 series-long-form / story-engine 里描述格式，没有进模板。如果希望模板里直接有这些节，需要主会话或负责系列简报模板的 lane 加。
5. **改编项目的立项候选**（premise-novelty §6 第 7 条）：原著核心设定算固定候选、另补 ≥5 个"同一原著的不同改编方向"，是我为了让"≥6 候选"门与改编兼容而定的规则，原套件没有。
6. **导演阐述的镜头语言部分**没有搬到任何地方，理由是它和 drama-forge 已定的节奏下限、长镜头合并、styles.md 锁定重复；若视觉 lane 认为"跨集阶段的镜头语言职责"仍有价值，可以由它补进 storyboard-keyframes。

## 总装补记（2026-09-26）

- `novel_index.py`、`episode_intake.py` 已由总装原样迁入 `drama-forge/scripts/`（只把报错文案里的 "short-drama" 改成 "drama-forge"）；两套 5 项自测并入 `scripts/merged_selftest.py` 的 `test_novel_index`、`test_episode_intake`，原来的两个 `selftest.py` 不再单独迁。adaptation.md 末尾说明已同步。
- 上文"其他文件里的残留指向"四条已处理：SKILL.md 的深挖一节改成 drama-forge 内部文件索引、阶段表 A 行补 genre-cards / series-long-form、新增 A0 行；market-hits 两处指向已删；pipeline-contract §1 已补 `输入/`、`项目开发/原著分析/`、`改编契约.md`、`跨集记忆.md`、`原稿/`。
- series-long-form §9、adaptation §10 的审查问题已移入 review-checklists §S、§R2，原处留引用和失败征兆。
