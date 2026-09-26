# 合并台账：视频提示词与生产（lane: video-produce）

来源：`short-drama-video-prompts/`、`short-drama-produce/` 全部文件（共 42 个，含缓存与会话状态文件）。
落点缩写：**GEN** = `references/video-prompts-general.md`；**H3** = `references/video-prompts-h3.md`；**SD** = `references/video-prompts-seedance.md`（新建）；**PR** = `references/production-and-review.md`；**PV** = `references/providers.md`（新建）；**PY** = `scripts/providers.py`（新建）；**ST** = `scripts/merged_selftest.py` 的 `test_video_produce_providers`（`scripts/selftest_providers.py` 只是单独运行它的入口）。

处置：**搬**（写进 drama-forge，指明位置）／**重复**（drama-forge 已有，指明位置）／**不搬**（写明原因）。

## short-drama-video-prompts

### SKILL.md
- 入口与参考准备（REF/PLAN 槽位、图生/文生判定、"待补参考图"停在提示词之前、分镜 owner 刷新绑定）→ **不搬**：drama-forge 的参考图、起始帧由 F/G 阶段自动生成并逐张目检，没有"创作者自己挂图"的 PLAN 路线；五文档字段（MOTION/SHOT/IMG 标题、`输入参考图`、`静态视觉锚点`、`> ` 引用块）与 drama-forge 的 shots.json 数据模型不同。其中"参考槽位用途决定模式"的实质 → **搬** H3 §11 模式表、PV §0 参考约束。
- 目标模型点名要先落到项目档案 → **重复**：SKILL.md 硬约束 1b + `drama.json` 的 `video_dialect`/`profiles`；方言路由 → **搬** GEN 开头（按 `video_dialect` 只读一份方言）。
- 工作流 5（时长落在模型原生区间、台词容量）→ **重复** H3 §1、§3。6–10（锁定、起点→唯一动作→终点、连续性锁锁面）→ **重复** GEN §1–3、H3 §4、visual-assets `locks[].phrase`。11（字幕层关闭、画内 exact_readable 文字）→ 字幕关闭 **重复** H3 §1/§9 头部句；画内可读文字 **不搬**：与 drama-forge 硬约束 4"生成画面不出字、字全部后期叠加"冲突。12（声音同轨完整时间线、逐字只出现一次、上游已确认的发声边界末尾合并写一次）→ **搬** GEN §9"声音同轨的模型要写完整的声音时间线"。13（相容性自检）→ **重复** GEN §10。15（相邻段默认续接上一段实际结果）→ **搬** SD §5、H3 §11"续接"，但改为**用户决定是否续接**（drama-forge 默认一镜一次起始帧生成，续接改变生产路由与成本，写进决策记录）。
- 提示词要求（从可见起点到可验证终点、交接不跨镜省略、正文不含路径/QA）→ **重复** GEN §2–3、§7，交付文本部分 **搬** GEN §9b。VID-25 引文四字以上必须来自剧本 → **重复** G09/G10（台词逐字）。
- 创作者口味（0.5 秒内开口、无台词镜写 says nothing、画质不是重点）→ **重复** H3 §3、§1、SKILL.md 硬约束 6。
- 时间线音乐章节 → **搬** PV §5（配乐任务前写清起止、剧情作用、进出、ducking）；实现归剪辑 **重复** edit-and-delivery。静态漫剧跳过运动提示词 → **不搬**：drama-forge 七种画风都走视频生成，无静态漫剧形态。
- 完成与投产（转 produce 先展示 job 并取得确认）→ **不搬**：与 drama-forge 全自动冲突，改为 runtime-boundaries 的批次授权 + 决策记录；付费授权与模型选择仍由用户（硬约束 1、1b）。

### agents/openai.yaml
- OpenAI 界面显示名与默认提示 → **不搬**：drama-forge 有自己的 `agents/openai.yaml`，岗位由 SKILL.md 硬约束 9 定义。

### references/minimax-h3.md
- 推荐档案 JSON（4–15 秒、四种生成模式、同轨声音）→ **重复** drama.json `video_dialect`/`shot_seconds`；型号差异 **搬** H3 §11、PV §2。
- 结构字段英文、台词原文 `<d>[语种]`、不加外语前导 → **重复** H3 §1、§3（G44）。
- 点名 H3 不等于选了文生 → **不搬**：drama-forge 永远先出起始帧。
- 三段结构、`[Shot N]` 切镜时间戳与官方切镜动词 → 三段 **重复** H3 §1；镜内切镜 **不搬**为用法：与 drama-forge 头部句 "no cuts"、一次生成一个镜头冲突，H3 §11 写明不用 `[Shot 2]` 与 `<scenetrans>`。
- 首尾帧正文顺序 → **搬** H3 §11。参考图对齐句（未 A/B）→ **不搬**：来源自己标"待自测"，按 SKILL.md 修改纪律先记模型观察。
- 风格保持（非真人不用 handheld/realistic、字幕声明、远景用背影）→ 前两项 **重复** H3 §9 + styles.md §1；远景背影 **搬** H3 §6 末。
- Hailuo 方括号运镜不属于 H3 → **搬** H3 §6。
- 无对白镜（写声轨、`non_diegetic_music: N/A`、嘴部按表演）→ **重复** H3 §1、GEN §7（不把需要喘气的人写成闭嘴）。
- 选哪一种模式（用途组合 → first_frame / first_last / reference）、不用只给尾帧的 L2VA → **搬** H3 §11 模式表。
- Full-reference 六段、一次整体提交、`<Picture N>` 按顺序编号、subject_definitions / retention_analysis 句式与保留强度词、每张图只负责一件事、不为多模态全挂 → **搬** H3 §11（例子改写成本项目的高中生/身份图/底板）。PLAN 槽位写法 → **不搬**（同上，无 PLAN 路线）。
- 素材数量上限、H3-Max 差异 → **搬** H3 §11、PV §2、PY `compile_minimax_video` 查个数。
- 连续段（reference_video + reference_image，不标 first_frame）→ **搬** H3 §11、PV §2。
- 时长 4–15 整数、正文秒数不能代替请求 → **重复** H3 §1。
- 对白容量 4.1 字/秒、语速描述放 `<d>` 外、`<cutoff>` 只用于剧本要求的截断 → 前两项 **重复** H3 §1、§3；`<cutoff>`/`<scenetrans>` **搬** H3 §11。
- 说话人绑定、画内他人 lips closed、骑手 3 次 2 次实测 → **重复** H3 §2。
- 参考音频 reference / fully_copy / partially_copy 语义与核听 → **搬** H3 §11。
- Context-IR 不替代对白预算 → **搬** H3 §11。
- 官方来源链接 → **搬** H3 来源节。

### references/seedance-2.5.md
- 推荐档案、中文自然指令、`@图片N` 绑定、4–30 秒 → **搬** SD §1–2、§6。
- 短单镜顺序、多镜时间段 `[0:00–0:03]` 不重叠不留空 → **搬** SD §4。
- 每次提及重复绑定、素材只负责一件事 → **搬** SD §2、GEN §7b。
- 多镜容器（参考清单重映射、容器不保证一致性、切口与一镜到底）→ **不搬**：drama-forge 一次生成只装一个 shots.json 镜头，审片/取用/重拍按镜记账（SD §6 写明原因）；30 秒长时长可用于长镜头合并，上限仍取 `shot_seconds.max`。
- 首尾帧两个位置、尾帧按已接受终点出、编号不跳号、不套 H3 互斥 → **搬** SD §4、PV §3。"套件内生产入口见 storyboard 首尾成对"→ **不搬**（指向子 skill 的链接）。
- 音色参考 reference_audio（五文档无音频绑定路径）→ 能力 **搬** SD §4；五文档字段限制 **不搬**（数据模型不同）。
- reference / edit / extend 三类任务、API 条件、语义复判、`任务类型` 字段 → **搬** SD §4（字段改为 shots.json `seedance_task`，需主会话在 pipeline-contract 登记）、PY `compile_seedance` 查硬条件。
- 对白花括号、`<声音>`、`（音乐）`、`【字幕】`、非中文台词写语言、末尾发声边界 → **搬** SD §2；`【字幕】` 开字幕 **不搬**（硬约束 4），改为一律写无字幕、不出现 `【】`；`（音乐）` **不搬**为用法（配乐归剪辑层），改写"全程无背景音乐"。
- 连续容器默认 extend、待续接不可提交 → **搬** SD §5（改为用户决定续接，标 `continuation_pending`）。
- 时长（-1 自动、edit 保持原长、extend 只算新增、返回 duration 向下取整）→ **搬** SD §4、§6、PV §3。
- 官方依据链接 → **搬** SD 来源。

### references/seedance-2.0.md
- 推荐档案、4–15 秒 → **搬** SD §3、§6。
- 正文组织、只响应镜头序号不响应时间戳、社区 `0-3秒` 写法与官方冲突 → **搬** SD §3。三次小样本切点不均分 → **不搬**：本流程不做一次生成多镜。
- 花括号对白、`<声音>`、禁字幕写法 → **搬** SD §2。
- 重复绑定、"参考 @视频1"与"向后延长 @视频1"、实际尾帧、素材序号来自真实绑定 → **搬** SD §2、§3、§5。
- `duration: -1` 自动时长 → **搬** SD §3（本流程不用）。

### references/target-model-profile.md
- 十条能力轴 → **搬** PV §1（改成接新模型前写进决策记录的表）。
- 负面提示通道 none / field_nouns / field_zh_default → **搬** GEN §11。
- 声音同轨 vs 不同轨、封闭事件集合 → **搬** GEN §9、PV §1。
- 字幕层独立、画内 exact_readable → 字幕关闭 **重复** H3；画内文字 **不搬**（硬约束 4）。
- 参考条件方式表、锁面留在正文、互斥时整组走参考、编号一致 → **搬** H3 §11、GEN §7b；锁面 **重复** visual-assets。
- 未声明时写通用正文、未声明不是缺陷 → **搬** GEN 开头（没有方言文件时按通则写）。
- 档案写在 short-drama.json → **不搬**（drama-forge 用 drama.json）。

### references/motion-recipe.md
- VID-01/02/03/12 规则表述、字段必须写本镜具体内容（复制到下一镜仍成立就是没写具体）→ 起止只读 **重复** GEN §1、SKILL.md 修改纪律；"具体内容"判法 **重复** H3 §4 七项检查；补拍版覆盖映射 VID-12 → **重复** PR §6"回归六行义务"。
- 选择性变换 VID-11（触发、范围、结束几何、preserve_set）→ **搬** GEN §7d。
- 参考图用途、未验证观察状态 → **重复** production-and-review §4 目检（drama-forge 每张图都看过）；观察状态字段 **不搬**。
- 末镜交接 VID-09（下一集起点未定，不伪造 ID）→ **重复** screenplay §8b 集间接缝。
- 起止边界卡片、最少起点信息 → **重复** GEN §2、H3 §4（起点 = 起始帧姿态）。
- 有序动作按因果连接、心理词落为可见 → **重复** GEN §3、H3 §4、§5。
- 一个主导变化 → **重复** GEN §3、H3 §4。
- 表演五步（触发、接收、处理、决定、结果）→ **搬** GEN §5 表演弧词汇（与 performance-action-timing 合并）。
- 摄影机动机与路径 → **搬** GEN §8。
- 环境与声音：环境按需 **重复** GEN §6；"每镜至少写一条环境动态，静止背景不合格" **不搬**：与 drama-forge 硬约束 6e"环境动态仅在自然存在或承担情节时描述，静止背景本身不构成失败"冲突。声音时间线 **搬** GEN §9。
- 时间：节拍链、量级 **重复** H3 §4；锚点秒数 **搬** GEN §4；显式分段双向算术（超出/不足、并集判不足）**搬** GEN §4；`timing_plan.mode` 字段与 motion_timing_check.py **不搬**（jsonl 数据模型）。
- 结束报告 match/mismatch/unrealized → **搬** GEN §10。
- 七项可执行检查、两百字、合成示例 → **重复** H3 §4（七项检查、150–250 词）；示例 **不搬**（H3 §9 已有实战示例）。
- 不重复参考帧内容 → **重复** GEN §2。
- 常见问题列表 → **搬** GEN §12 反例速查（合并）。

### references/production-prompt-grammar.md
- 核心认知 1–2（从已接受起点、连续性靠前后镜比较）→ **重复** GEN §1–2、G26。
- 核心认知 3 + 参考绑定纪律（稳定索引每次提及都带、部分绑定比不绑更危险、编号不重排、同号一物、索引不进台词围栏）→ **搬** GEN §7b。
- 核心认知 4（台词相对动作的先后不可改）→ **重复** GEN §4、H3 §10 第 3 条。
- 核心认知 5（手部接触与交接可执行）→ **重复** GEN §7。
- 核心认知 6 / 五.1–5（exact-readable 优先于 no-text、参考图带字先裁清）→ 画内文字 **不搬**（硬约束 4）；参考图带字要处理 **重复** PR §4（contaminated 标签、重出）。
- 一、自然语言写法与量级属于本环节 → **重复** H3 §4（至少一处量级）。多段交付格式 → **不搬**（无交付档案/容器）。
- 二、本镜关键状态、空间连续（裸左右指画面左右、方位变体底板、声明省略）→ **重复** GEN §2、H3 §1、visual-assets §4b/G28、SKILL.md 6b。
- 三、能力三区（稳定/不稳定/超出）→ **搬** GEN §11。
- 四、项目参数只读 → **重复** drama.json。
- 五.6 社区固定尾缀不采用 → **搬** SD §2（Seedance 社区模板最常见）；H3 **重复**"不往提示词里堆负面词"。五.8 不用词表判审美 → **重复** SKILL.md 修改纪律（模型观察 ≥3 次）。
- 六、决策规则（并发过载拆镜、听者反应、台词负载、修订只改诊断变量）→ **重复** GEN §4/§11、H3 §3、§8。
- 七、范例 → **不搬**（H3 §9、GEN §7 已有同类示例）。
- 交付文本只含交付内容 VID-22 + 合成反例改写 → **搬** GEN §9b（改写为本项目口径）。
- 八、自检 → 新增项已并入 GEN §10。

### references/performance-action-timing.md
- VID-04/05 → 算术 **搬** GEN §4；动作负载靠审查判断 **搬** GEN §4 超载段。
- 动作预算不是计数器、先找 spine → **重复** GEN §3、H3 §4 优先级梯。
- 2–3 个递进节拍、塞五件事道具消失的实测、手指微动作写大配插入、起始帧停在起手前 → **重复** GEN §3、PR §4b 第 11 项（钱箱消失）、H3 §7、PR §4（停在动作之前）。
- 接触动作双人同框（reviewed_invariant）→ **重复** SKILL.md 硬约束 3 + storyboard-keyframes §9、GEN §7。
- 同时发生的合理用法 → **重复** H3 §4 并行通道。
- 角色不是情绪滑块、外显通道 → **重复** H3 §5 两个信号预算。
- 表情词避坑改写表（sneer/forced grin/plants himself 实测）→ **搬** GEN §5 改写表（H3 §5 写"改写表见 video-prompts-general §5"，但原 GEN §5 没有这张表）。
- 表演标尺（仅创作者声明时）→ **不搬**：drama-forge 用 `dialogue[].emotion` 的"情绪·强度·语速·音量"作为唯一强度来源（screenplay §4b），不另设标尺。
- 表演弧 agenda/receive/mask/visible_leak/choice/landing、注意交接、不给全员复制震惊 → **搬** GEN §5。
- 反应的对象 → **重复** H3 §8。
- 相对时间优先、不用秒级时间戳控制动作开始、动作以实测为准 → **重复** GEN §4、PR §1 H3 实拍经验、quality-contract。
- 显式时间示例 → **搬** GEN §4（算术规则）。
- 对白预算、例子（7 秒镜装 8–10 秒台词）、H3 4.1 字/秒、标点不计 → **重复** H3 §3（发声窗口公式、4.1 字/秒、G04 用 speech_rates）。
- 对白太长的选项（不能自行删字）→ **重复** H3 §3 降负载顺序。
- 长镜头同一个人多节拍（2026-09-26）→ **重复** GEN §3b。
- 超载征兆、修订优先级 → **搬** GEN §4；Reviewer 证据格式 → **重复** PR §6 finding 格式。

### references/camera-audio-continuity.md
- VID-06 同区间不能又锁又动 → **搬** GEN §8。VID-07 口味 → **重复** drama.json 头部句。
- CON-01 终点与下一镜起点一致 → **重复** G26、GEN §10。
- §0 视线看说话对象 → **重复** SKILL.md 6f、GEN §5、H3 §3（G43）。
- §1 运镜动机、锁定写三样、移动写五样、移动不重置地理 → **搬** GEN §8（锁定一项原 H3 §1 已有简版）。
- §2 相对运动、运镜术语属于方言 → **搬** GEN §8；H3 词表 **重复** H3 §6。
- §2 切镜边界（镜内不藏切）→ **搬** GEN §8、GEN §12。
- §3 环境运动选择规则 → **重复** GEN §6；"每镜至少一条环境动态，静止背景不合格"、"背景人写清在做什么"作为强制项 → **不搬**：与硬约束 6e 冲突（H3 §4b 已有按需写背景人的写法）。
- §4 精确引用、同一句台词跨镜延续 → 前者 **重复** G09/G10；跨镜延续 **搬** GEN §9。
- 配乐归时间线层 VID-14、只否定配乐层 → **搬** GEN §9；**重复** edit-and-delivery 配乐节、H3 `N/A`。
- 环境底声跨镜相接 → **搬** GEN §9（H3 §1 原有一句）。
- Delivery 与 voice_direction → **重复** H3 §1（`voice` 同一段描述，G21）、§5。
- 音频矛盾 → **搬** GEN §12（语义发明反例）。
- §5 可改 / 不可改清单、revision request 格式 → **重复** SKILL.md 修改纪律、GEN §11、PR §6（finding 含最小修复）；格式本身 **不搬**（drama-forge 不走跨 owner 修订请求，写作阶段由 writer/reviewer 自动改）。
- 首尾帧两端收窄运动、终点对照 end_boundary 不对照尾帧 → **搬** GEN §7c。

### references/generability.md
- 适用条件（仅生成画面）→ **不搬**：drama-forge 全部是生成画面，永远适用。
- 判据"日常影像常见吗"、念给没读剧本的人比划 → 前者 **重复** H3 §7"常见动作放心写"；比划测试 **搬** GEN §11。
- 四类高风险、戏剧信息来自组合与时机、改写五步、失败征兆 → **重复** H3 §7（高风险清单、改写阶梯、笔记本例子）。

### references/stage-contract.md
- 阶段只拥有 MOTION 项、参考准备例外 → **不搬**（五文档所有权模型；drama-forge 用阶段 E 与岗位分工）。
- VID-01…25、CON-01…07 规则表与四级分类 → 分类 **重复** PR §6"四级规则"；各条实质已按上面逐条落点（VID-04/06/11/21/22/23 搬进 GEN；VID-13/15/19/20 容器与路由见 delivery-profile；CON-02 **重复** scene-state-and-reveal.md；CON-07 **重复** visual-assets 锁面）。规则编号本身 **不搬**：drama-forge 用 G00–G45 机械门，不引入第二套编号。

### references/delivery-profile.md
- 交付档案、槽位语义（空间/姿态/位置/表演）→ **不搬**：drama-forge 没有交付档案层；槽位要回答的问题 **重复** H3 §4 七项检查、GEN §2。
- 交付路由：逐镜 / 多镜打包 / 单次长生成 / 续接 → 逐镜 **重复**（默认）；打包与单次长生成 **不搬**（一次生成一镜，SD §6 写原因）；续接两项真实输入、不回写观察状态、待续接不可提交 → **搬** SD §5、H3 §11。
- 容器算术、成员资格、VID-15 全集账目 → **不搬**（无容器；每镜 `seconds` 与 cut_order 由 shots_tool 管）。单镜内分段双向和 → **搬** GEN §4。
- 逐字对白围栏 → **重复** H3 `<d>`；口语语言写在声源标识 → **重复** G44。
- 执行触发词逐字保留、不进围栏、失败是安静的 → **搬** SD §5（续接字样）。
- 合成示例、自检 → **不搬**（依赖档案记号）。

### references/review-and-fixtures.md
- 审查顺序、证据量表 13 维 → **重复** PR §5 视频审片三层 + reviewer 流程（SKILL.md 每次执行第 3 条）。
- 完成前结构检查 → **重复** shots_tool 门（G04/G05/G26 等）+ GEN §10。
- 合成正例（藏登记簿）→ **不搬**（H3 §9 已有实战正例）。
- 反例 A–G（外观倾倒改边界、动作超载、camera 矛盾、音频语义发明、段内藏切、微计量、整段独白）→ **搬** GEN §12 反例速查（改写压缩）。

### references/.omc/state/sessions/57c8a195-…/pre-tool-advisory-throttle.json
- OMC 插件的会话节流状态，不是技能内容 → **不搬**。

### examples/minimal-music-specs.jsonl
- 一条纯配乐规格示例（叙事功能、配乐提示词、入出与 ducking）→ **搬** PV §5（提示词示例原样保留英文，字段改为剪辑单/决策记录里的文字说明）。

### assets/music-spec.jsonl.md
- 配乐规格字段（scope、narrative_function、prompt 只写音乐意图不写艺人/模型、song 必须有用户歌词、mix_intent）→ **搬** PV §5；jsonl sources 头 **不搬**（数据模型不同）。

### assets/motion-terminal.example.jsonl
- 末镜 next_start_locator 示例 → **不搬**：jsonl 数据模型；末镜交接 **重复** screenplay §8b。

### assets/delivery-container.jsonl.md
- 容器记录模板与校验点 → **不搬**（无容器，理由同 delivery-profile）。

### assets/video-prompts.md
- 结构化管线的《video-prompts.md》渲染模板（MOTION 章节、只读结束报告、待续接写法）→ **不搬**：drama-forge 用 `shots_tool.py render` 渲染分镜；结束报告三态 **搬** GEN §10；待续接 **搬** SD §5。

### assets/performance.fragment.json
- 表演弧与注意交接字段 → **搬** GEN §5（作为可选词汇，不加 shots.json 字段）。

### assets/coverage-scope.fragment.json
- 补拍/替代版覆盖映射字段 → **不搬**：drama-forge 重拍开新 take、改分镜走 E 阶段，义务保留由 PR §6 回归六行承担。

### assets/motion-spec.jsonl.md
- motion-specs.jsonl 完整字段模板 → **不搬**：数据模型不同（shots.json 已有 boundary、planned_action_window、gaze、end_state 等对应字段，见 pipeline-contract）；其中写作要点已按 motion-recipe 各条落点。

### scripts/motion_timing_check.py
- 显式分段超出/不足（并集）算术检查 → 规则 **搬** GEN §4；脚本 **不搬**：读 motion-specs.jsonl，drama-forge 的 shots.json 没有显式分段字段（`planned_action_window` 只是计划）。

### scripts/container_check.py
- 容器集合对账（一镜只进一个容器、不重不漏）→ **不搬**（无容器）。

### scripts/music_spec_check.py
- 配乐 jsonl 校验（无供应商字段、song 需歌词、scope 合法）→ 规则 **搬** PY `compile_minimax_music`（歌词必填/禁 lyrics_optimizer）与 PV §5；jsonl 引用解析 **不搬**。

### scripts/selftest.py
- music_spec_check 的 10 项离线测试 → **不搬**（被测脚本不搬）；配乐规则测试改写进 ST。

### scripts/__pycache__/music_spec_check.cpython-313.pyc
- 编译缓存 → **不搬**。

## short-drama-produce

### SKILL.md
- 硬闸门：prepare → 展示预览 → 用户看到预览后明确确认 → run 消费一次确认；任何变化确认失效；不自动准备下一批 → **不搬**：与 drama-forge 全自动冲突。改为 runtime-boundaries 的批次授权（范围、次数、成本上限一次给定，沿用明确授权）+ 决策记录；**付费授权与模型选择仍需用户**（硬约束 1、1b），范围或价格变化才补授权。
- job 来源选择器（IMG/MOTION/SHOT 标题、prompt 必须等于源文档可复制正文）→ **不搬**（五文档）；"送出的正文逐字取自 shots.json、不在 job 里改写" **搬** PV §8。
- PLAN 槽位拒绝 → **不搬**（无 PLAN 路线）。
- 本地参考 base64 data URI 直接送 → **搬** PV §0、PY `inline_references`。
- 输入选择：video 续接两项真实输入 → **搬** SD §5、H3 §11；tts 带情绪、四项整理、只有一个情绪词其余按"中"、剧本没情绪回剧本 → **搬** PR §10（补"其余按中"）；其余 **重复** PR §10。口音母语、`language_boost` 不用 auto、专名 `pronunciation` 核对 → **重复** PR §10、SKILL.md 6f；PY 把 `language_boost` 改为必填。music（已确认歌词、剪辑落点）→ **搬** PV §5。
- 一个 job 不混 modality、大批量拆小 → **重复** 硬约束 2（串行一次一个任务）、PR §9 预算。
- Adapter 边界（配置在项目外、argv 不走 shell、凭据只从环境）→ 凭据 **重复** PR §1.8、runtime-boundaries；外部 adapter 进程协议 **不搬**（drama-forge 直接调用脚本函数，不需要 stdin/stdout 进程协议）。
- 参考约束追加（中文名、用途、允许/不得控制）→ **搬** PY `with_reference_contract`、PV §0。
- 五个内置 adapter 说明 → **搬** PV §2–6、PY。
- 中断不等于重跑（提交即计费、任务号先落盘、orphaned → collect）→ **重复** runtime-boundaries、PR §1.2–1.4；PY 沿用同一账本。
- 结果与复核：TTS 听感五问、ASR 专名读错判不合格 → **重复** PR §10。"不能听音频时用电平/语速代理指标，全都一样就判平" → **不搬**：与 PR §10"没有听音能力时 RMS 和语速只能提供排查线索，不能推断情绪通过或直接触发重生成"冲突，以 drama-forge 为准。失败三路与被拒输入改写例 → 三路 **重复** PR §6；改写例 **搬** PR §6、PV §7。repeated_content 只是成本信号 → **搬** PR §9、PV §7。生产结束不自动剪辑、不自动复核 → **不搬**：drama-forge 全自动推进到审片与剪辑。
- 模型与档位由创作者指定、2026-09-24 改口 base50_sol → **重复** 硬约束 1b、drama.json `profiles`（项目值为准）。
- 安装维护自检命令 → **搬** PV §8（`merged_selftest.py -k providers`）。

### agents/openai.yaml
- 界面显示名 → **不搬**（同上）。

### references/adapter-contract.md
- job 文件字段（schema、source_entry、reference_bindings 16 个上限、outputs 目录白名单、overwrite 必须显式）→ 简化 **搬** PV §8 job 格式、PY `_refs`（label/role/may/must 必填、不重叠）；目录白名单与 source_entry **不搬**（五文档目录）；不覆盖 **重复** 硬约束 8（PY 输出已存在即拒绝）。
- adapter config / stdin / stdout 协议、私有快照目录、公开错误白名单 → **不搬**（进程协议不需要）；"错误里不带响应正文、提示词、路径、凭据" **搬** PY `ProviderError`、`urllib_transport` 不保留错误正文。
- Recovering a submitted task（handle 早于轮询、collect 不需确认）→ **重复** runtime-boundaries；PY 在拿到任务号后立即写 `submitted`。
- Capability sources（中转可能只暴露子集，区分实测路径与原生契约）→ **搬** PV §2 首段（中转档位名不是官方模型 ID）。
- Operational reconciliation / audit（终态失败、重复内容指纹、输出字节变化、quality_verdict not_assessed）→ **搬** PV §0"成功不等于质量"、PV §7 后两条、PR §9 指纹计数；audit 命令本身 **不搬**（账本由 h3_client `unresolved`/`pending` 管）。

### references/providers/seedance.md
- 环境变量、无默认模型、比例/时长区间、duration -1、role 与 `@图片N`、data URI 与保守上限、2.0/2.5 措辞差异、edit/extend 硬条件、轮询端点 → **搬** PV §3、PY `compile_seedance`、SD §3–4。

### references/providers/minimax-speech.md
- 必填 model/voice_id、不内置音色清单、只用预置音色不克隆、请求形状、emotion 白名单与官方已知差异、语气词与停顿、剥标注再做字幕/ASR、language_boost 不收 auto、音色母语、pronunciation_dict → **搬** PV §4、PY `compile_minimax_speech`；情绪白名单取六个共有值（去掉 neutral，见"拿不准的取舍"）。

### references/providers/gpt-image-2.md
- 环境变量、generations/edits 分流、固定模型与 n=1、尺寸/质量/背景/审核参数、不支持透明、不传 input_fidelity → **搬** PV §6、PY `compile_gpt_image`。

### references/providers/minimax-music.md
- music-3.0、hex、纯配乐与歌曲、歌词必须是已接受原文、禁 lyrics_optimizer、格式 → **搬** PV §5、PY `compile_minimax_music`。

### references/providers/minimax-h3-video.md
- 环境变量（模型、分辨率集合、时长区间必须显式）、ratio 规则（文生必填非 adaptive）、不估语速、7000 字符、五种 role、素材上限、首尾帧与参考互斥、续接用 reference_video + reference_image、data URI 与单文件上限、轮询端点、同轨声音与方言影响 → **搬** PV §2、PY `compile_minimax_video`、H3 §11。

### scripts/provider_adapters.py
- 五个 compile 函数、参考约束追加、data URI 内联与上限、文件头校验、HTTP 错误分类、轮询与下载、handle 先落盘 → **搬** PY（重写为 drama-forge 口径：复用 `h3_client.Client` 的账本/锁/STOP/DEADLINE；模型 ID 由 job 显式给出；5xx 按提交结果未知处理而非可重试；输出已存在即拒绝；`language_boost` 必填）。外部进程 CLI（stdin job → stdout outputs）**不搬**。
- 自带 `--selftest` → 改写进 ST。

### scripts/production_tool.py
- 确认闸门（prepare/confirm/run、指纹绑定一次性确认、运行锁、私有输入快照、no-follow 目录、审计）→ **不搬**：确认闸门与全自动冲突；快照/锁/审计由 drama-forge 现有账本（`submission_intent`、`unresolved`、`reconcile`、`pending`）承担；五文档来源校验不适用。可取的"同一指纹重复提交是成本信号"已 **搬** PR §9、PV §7。

### scripts/fixture_adapter.py
- 离线假 adapter（含"提交后崩溃"场景）→ **不搬**脚本；同类场景在 ST 用假传输层覆盖（成功链路、4xx 拒绝、网络断开、5xx 未知、未决阻塞）。

### scripts/selftest.py
- 确认闸门与三个 compile 的离线测试 → 闸门部分 **不搬**；compile 部分改写进 ST。

### scripts/__pycache__/production_tool.cpython-313.pyc、scripts/__pycache__/provider_adapters.cpython-313.pyc
- 编译缓存 → **不搬**。

## 拿不准的取舍（交主会话定）

1. **MiniMax 语音情绪白名单**：原 adapter 收六个加 `neutral`；官方 2026-09-25 已不列 `neutral`，另有 `calm`/`fluent`/`whisper`（型号限定）。PY 只收六个共有值，平读不传；若用户要用 `calm` 或 `whisper`，需要先实测再放开。
2. **HTTP 5xx 的处置**：原 adapter 把 5xx 当"可重试的失败"。PY 改成 `submission_unknown`（网关超时时后端可能已受理并计费），代价是 5xx 后要人工 `reconcile` 才能继续。
3. **新增 shots.json 字段未登记**：SD 里用了 `seedance_task`（2.5 任务类型）和 `continuation_pending`（续接等待）；pipeline-contract.md 不在本 lane 可写范围，需主会话登记或改名。
4. **门脚本不认 Seedance 方言**：`shots_tool.py` 的 G09/G10/G17/G44 只认 H3 `<d>` 标记，`produce.py` 只对接 H3 中转；用 Seedance 前需要扩展门脚本与 produce（SD §7 已写明暂行做法）。
5. **本 lane 之外仍指向被删子 skill 的位置**：`SKILL.md`"深挖时读的本地套件"一节（`short-drama-video-prompts/references/minimax-h3.md`、`seedance-2.5.md`）、`styles.md` 第 315 行（"读本地 short-drama-video-prompts/references/seedance-2.5.md"）应改指 `video-prompts-seedance.md`；SKILL.md 阶段表 F–H 可加 `providers.md` 与 `video-prompts-seedance.md`。
