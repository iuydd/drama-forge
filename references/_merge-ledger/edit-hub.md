# 合并台账：剪辑交付与总控 lane

来源：`short-drama-edit/` 与 `short-drama/`（总控）下的全部文件，共 50 个（按 `find -type f` 逐个列出，一个不漏）。
落点只在本 lane 可写的文件：`references/edit-and-delivery.md`、`references/styles.md`、新建 `references/project-hub.md`、新建 `scripts/hub_tool.py`、新建 `scripts/merged_selftest.py`（`test_hub_tool`）。
标记：**搬入** = 已改写进 drama-forge；**重复** = drama-forge 已有，指出位置；**不搬** = 写明原因。

## short-drama-edit/

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 进入条件＝素材字节当前可读（提示词写完/任务成功不算）；先看完整素材标可用带再定入出点；剪辑只取舍不改写上游；未采用镜头分"缺文件/质量不可用/叙事取舍"；同源两段不重叠、有意重复要写理由；目标时长区分参考与硬要求；技术成功不等于质量结论；先改剪辑单再渲染；重剪保留未受影响段 | **搬入** edit-and-delivery §1（进入条件）、§1b（可用带）、§2 drop 三类理由、§2b（权限、重复使用、目标时长、不机械补时长）、§6（剪辑单可复现、先改记录再出片、重剪不动未受影响镜）、§7（技术结果不是质量结论）。`## CUT-…`/`MOTION-…` 剪辑单格式与 `edit_tool.py check/render/verify` 命令 → **不搬**：drama-forge 的剪辑单由 cut.py 从 review.json 自动生成，镜号体系是 `EP001-S07`，两套格式不能混 |
| `agents/openai.yaml` | 子套件的显示名与默认提示 | **不搬**：drama-forge 有自己的 `agents/openai.yaml` |
| `assets/剪辑单.md` | 手写剪辑单样例（CUT 块、取舍理由、未采用镜头两类理由示范） | **不搬**格式（cut.py 自动写剪辑单，edit-and-delivery §6）；两类理由的示范并入 §2 drop 理由 |
| `assets/remotion/README.md` | 可选 Remotion 字幕叠层的安装与取舍（Node 依赖、逐帧无头浏览器渲染、并发压 2） | **不搬**：drama-forge 字幕、面板、印章字都用 PIL 出 PNG 再 overlay（edit-and-delivery §3–4、§8），不依赖 libass，也不需要 Node；Remotion 路线慢且吃内存，没有 drama-forge 缺的能力 |
| `assets/remotion/package.json` | Remotion 依赖清单 | **不搬**（同上） |
| `assets/remotion/remotion.config.ts` | Remotion 渲染配置 | **不搬**（同上） |
| `assets/remotion/tsconfig.json` | TS 配置 | **不搬**（同上） |
| `assets/remotion/src/index.ts` | 入口 | **不搬**（同上） |
| `assets/remotion/src/Root.tsx` | 合成定义 | **不搬**（同上） |
| `assets/remotion/src/Subtitles.tsx` | 字幕组件（CSS 样式、折行、入场） | **不搬**（同上；cut.py 已有按像素宽换行、标点后断行、面板入场动画） |
| `assets/remotion/src/font.ts` | 字体加载 | **不搬**（同上；drama.json `fonts.sub` 已有字体候选） |
| `assets/remotion/src/schema.ts` | 字幕 cue 的 schema | **不搬**（同上） |
| `references/cut-craft.md` | 入出点按信息/表演/节奏选；对白可在句中切画面但音轨连续；镜序调整查因果、视线、空间、揭示、声音；重复信息无新作用才删；转场不能替代缺失内容；删短后不机械补时长；目标时长参考 vs 硬要求；"项目例外"节奏下限与面板样式 | 句中切画面（J/L-cut）、节奏下限、面板科技感 → **重复** edit-and-delivery §2（J/L-cut、节奏下限表）、§4（panel）。"不在句中切"与"可以句中切画面"冲突 → 以 drama-forge 为准（一句台词在一个镜头里说完，硬约束 6f），不搬"句中切"。不机械补时长、参考 vs 硬要求 → **搬入** §2b。转场不替代缺失内容 → **搬入** §1b 第 3 条的精神（缺信息回重拍/改分镜）。镜序调整后复核 → **重复** §6（调整 cut_order 后复核预演和信息权限） |
| `references/delivery-verify.md` | 交付核对表（时长与切点、内容覆盖、台词、边界帧、声音、字幕、画内文字、画幅帧率、接镜色彩）；区分实测/人工判断/未测；分段色彩观测只是筛查；有意黑场静默按意图判断；交付物清单 | 大部分 **重复** edit-and-delivery §7 五步。**搬入** §7：边界帧抽帧命令与判断、有意黑场按意图判断、交付物清单、`hub_tool.py measure` 自动报数字与"未测"；接镜色彩 → §5b |
| `references/generated-footage.md` | 逐段看完整素材、0.25–0.5 秒抽帧、缺陷附近逐帧；可用带比计划短时三种处理；不为避缺陷丢故事信息；画面不可用而对白完整可保声换画；缺陷反馈上游的写法（时间+画面+希望保住的状态）；接镜色彩（同场景同光态分组、可比区域、全画面均值只作筛查、亮度/饱和/色温三项及范围、先小幅校）；颗粒 0–20 | **搬入** edit-and-delivery §1b（可用带、三种处理、保声换画用 `audio_from`、缺陷反馈写法）、§5b（接镜色彩与颗粒，并新增 `hub_tool.py measure/grade` 实现逐镜测量与校色，因为 cut.py 没有这项能力）。"不把某次结果当规律" → 指向 project-hub §4 与模型观察 |
| `references/sound-and-subtitles.md` | 声音接缝回听；内置工具不执行"声音"行的混音描述；loudnorm 两遍也可能退回动态处理、输出 48 kHz；台词先定位发声区间再回听；重出素材后重测字幕时间；字幕逐字取剧本；字幕数值表；竖屏安全区；ffmpeg/Remotion 两条渲染路线；sidechaincompress 压配乐 | 字幕取剧本、数值表、安全区、sidechain、真峰 → **重复** edit-and-delivery §3、§5（其数值表本来就是抄自 drama-forge）。重出后重测 → **重复** SKILL 硬约束 11（重拍后重新 mark）与 quality-contract（不跨 take 继承）。**搬入** §5 响度：loudnorm 退回动态处理、目标值不是实测值、48 kHz、整片达标不等于每句清楚。Remotion 路线 → **不搬**（见上） |
| `references/stage-contract.md` | EDT-01…18 规则表与四级分级；剪辑与上游的分工表；生成结果与上游不符时记事实、不改上游声明 | 规则分级 → **重复** production-and-review §6（四级规则）。EDT-01/02/06/07/11/13/15/16/17 → **搬入** §1b、§2、§2b、§5b、§7（按 drama-forge 口径改写，不保留 EDT 编号）。EDT-12 "竖屏默认烧字幕" → **重复** §3（字幕一律后期烧）。EDT-14 "剪辑节奏、是否保留停顿是创作者口味、不算缺陷" → **不搬**：与 drama-forge 节奏下限（硬约束 6f、edit-and-delivery §2 节奏下限表）冲突，以 drama-forge 为准。EDT-18 颗粒 → **搬入** §5b。分工表 → **搬入** §2b（剪辑不改台词/职责/起止，回 C 或 E） |
| `scripts/edit_tool.py` | 解析 CUT 剪辑单；check（素材比剪辑单新、区间自洽、同源不重叠、字幕在剧本里）；render（切段、拼接、ASS/Remotion 字幕、逐段 eq/colorbalance 接镜校正、整片动态颗粒、两遍 loudnorm 48 kHz）；verify（时长、画幅帧率、LUFS/真峰、逐段平均亮度与蓝减红、诚实"未测"） | 剪辑主链 → **重复** cut.py（取用、字幕、叠加、混音、响度、剪辑单）。cut.py 缺的两项 → **搬入** 新脚本 `scripts/hub_tool.py`：`grade`（按 `审查/<EP>-grade.json` 逐镜 eq/colorbalance + 整片 noise 颗粒，范围与 edit_tool 一致，输出 `_graded.mp4` 不覆盖原片）、`measure`（时长差、画幅帧率、ebur128 LUFS/真峰、静音占比、逐镜亮度与蓝减红、未测项）。CUT 格式解析与 check → **不搬**（格式不同，drama-forge 的对应检查在 shots_tool 门与 quality-contract 准入里） |
| `scripts/selftest.py` | edit_tool 的自测（字幕几何、时间、接镜、多句字幕、过期窗口、ASS 转义、Remotion、颗粒、缺镜报告） | **不搬**原测试（测的是 edit_tool）；新功能的测试写成 `scripts/merged_selftest.py::test_hub_tool`（导出排除项、覆盖保护、剪辑单解析、grade 滤镜与越界拒绝、有 ffmpeg 时实跑 measure/grade） |
| `scripts/__pycache__/edit_tool.cpython-313.pyc` | 字节码缓存 | **不搬**：编译产物，无内容 |

## short-drama/（总控）

| 来源文件 | 独有内容要点 | 处理 |
|---|---|---|
| `SKILL.md` | 五文档路由表；只在真实创作分叉询问；范围完成一次回报；视觉依赖对账；缺参考图时三条路；会话里点名的目标模型要立刻写进项目档案，否则下一轮退回默认；init 带齐已确认的集数/时长/画幅；Dashboard 启停；`export` 快照（manifest、checksums、排除私有、`asserts_approval: false`）；`package/verify` 审批包 | 路由表 → **不搬**（子套件删除，drama-forge 用阶段 A–J）。只在真实分叉停下、范围内连续执行 → **重复** SKILL 硬约束 1 与 runtime-boundaries。用户口头定的模型/时长/画幅当场写进配置 → **搬入** project-hub §2（按 drama-forge 字段 `profiles`/`episodes`/`target_seconds`/`aspect`，且只写用户明说的，符合硬约束 1b）。export → **搬入** project-hub §3 + `hub_tool.py export`。Dashboard → 见 dashboard 行。缺参考图三条路（创作者自己出图挂载 `PLAN-…`、明确选文生视频）→ **不搬**：drama-forge 阶段 F 自己出参考图，且硬约束"不静默降级为文生视频"（visual-assets §10）。`publish/accept/set-authority` 三步接受档案、`package/verify` 审批包 → **不搬**：逐项人确认与全自动冲突，改为决策记录（project-hub §5） |
| `agents/openai.yaml` | 显示名与默认提示 | **不搬**：drama-forge 有自己的 |
| `assets/creator-decision.example.jsonl` | 创作者决策记录样例（视觉方向、剧本接受、调度方案选择，带 supersedes） | 决策记录本身 → **重复** `assets/templates/决策记录.md`。**搬入** project-hub §5：决策记录该记的类别表（立项与画风、写作接受、调度方案选择、生产与审片、剪辑交付、未决），并把"等创作者接受"改写成自动决策 + 记录；JSONL 格式不搬（drama-forge 用 Markdown 表） |
| `assets/production-observation.example.jsonl` | 生产观察记录字段：准确的提示词版本、参考槽位与顺序、生产配置、观察区间、直接观察、局限、只对本项目有效、观察方式 | 模型观察规则 → **重复** `assets/templates/模型观察.md` 与 SKILL「修改纪律」（≥3 次升级）。**搬入** project-hub §4：每条观察必须写清的六项（条件、区间、直接观察、局限、方式、有效范围） |
| `assets/reference-observation.example.jsonl` | 输入参考图观察：可见文字/水印、裁切遮罩、能支撑的身份/地理证据、文字政策结论、未验证风险 | 有字有水印就重出 → **重复** visual-assets §8；真人素材 → visual-assets §11。**搬入** project-hub §4「参考图观察」：接入前看一遍记什么，没看过写"未验证" |
| `assets/project-template/short-drama.json` | 项目模板：语言、画幅、提示词语言、集数、目标时长、语速、visual_direction / production_profile / delivery_surface（平台遮挡区）状态 unset/accepted | **重复** `assets/drama.template.json`（language、aspect、prompt_lang、episodes、target_seconds、speech_rates、profiles、style_preset）；平台遮挡区 → **重复** edit-and-delivery §3 竖屏安全区。unset/accepted 状态机 → **不搬**（人确认流程；drama-forge 用 null 与决策记录） |
| `assets/dashboard/index.html` | 本地"短剧创作台"网页：项目/集列表、阅读剧本、编辑正文、保存 | **不搬**，改为只读 `hub_tool.py overview --html`。原因：Dashboard 编辑的是五文档结构；drama-forge 的分镜/提示词 md 由 `shots_tool.py render` 从 shots.json 生成，网页编辑会被下次 render 覆盖；进度数据来自 shots.json/review.json/账本，结构完全不同，移植要重写服务端与前端，收益只是一个进度页。说明写在 project-hub §1 |
| `assets/dashboard/app.js` | Dashboard 前端逻辑（会话令牌、读写文件、编辑模式） | **不搬**（同上） |
| `assets/dashboard/styles.css` | Dashboard 样式 | **不搬**（同上；overview HTML 自带浅/深色样式） |
| `references/audience-reveal.md` | 每个有揭示时机的事实写：事实来源、本镜权限、可见/可听载体、释放时机、保护方法、戏剧理由；"来者认识主角"和"来者是谁"是两件事分开扣；说不出何时释放就是没设计完 | **大部分重复** scene-state-and-reveal.md（三本账、隐藏项写计划揭示镜与证据）。水墨"留白＝设计过的未知，要说得出何时释放" → **搬入** styles.md §13.4。独有的"身份与认识关系分开扣""保护方法一项" → 本 lane 不能写 scene-state-and-reveal.md，**列为拿不准**，建议主会话在该文件"观众认知"条补一句 |
| `references/contract-and-ownership.md` | 工作流不是瀑布；三种输出语言互相独立；稳定可见 ID；REF/PLAN 槽位；规则四级；普通创作不联网、凭据只在 adapter | 语言独立 → **重复** drama.json 的 `language`/`dialogue_lang`/`prompt_lang`。稳定 ID → **重复** pipeline-contract §2。规则四级 → **重复** production-and-review §6。凭据 → **重复** SKILL Quick Start（token 只从环境读）。REF/PLAN 槽位 → **不搬**（drama-forge 用 refs.json 与 `frame_refs`）。不写绝对路径、私有输入 → **搬入** project-hub §7 |
| `references/creator-documents.md` | 五份创作文档的写法：剧本标签、视觉设定条目、画面代称、连续性锁（LOCK/锁面逐字携带）、分镜字段、三类依据不得混用、REF/PLAN 语法、视频提示词字段、提示词正文可直接复制 | 剧本标签 → **重复** screenplay.md 与 pipeline-contract（`## EP001-SC001` 场头同格式）。连续性锁与锁面逐字携带 → **重复** visual-assets §6（G23）。分镜字段 → **重复** shots.json 字段（pipeline-contract §4）。REF/PLAN、画面代称、五文档格式 → **不搬**：与 drama-forge 结构（shots.json 为真相、md 由 render 生成）冲突 |
| `references/creator-workflow.md` | 五文档是唯一落盘、单集不落 JSON；请求范围与只在三处停；一句话交代范围的四件事；生产 preview→confirm→run；连续场次"上一段视频+尾帧接力" | 单集不落 JSON → **不搬**（与 drama-forge 的 shots.json/review.json 冲突）。只在三处停 → **重复** runtime-boundaries。preview→confirm→run 逐次确认 → **不搬**，drama-forge 是授权范围内自动连续执行（硬约束 1），付费授权与模型选择仍由用户定（project-hub §5）。尾帧接力 → 属视频提示词/生产 lane，本 lane **不搬**，drama-forge 已有 `frame_parent`（pipeline-contract §4） |
| `references/knowhow-index.md` | 主题→负责子技能路由表；规则四级；冲突优先级（已接受事实 → 单集契约 → 各阶段规则表 → 题材卡/形态卡） | 路由表 → **不搬**（子套件删除）。四级 → **重复** production-and-review §6。冲突优先级 → **搬入** project-hub §6，改写成 drama-forge 六层（安全授权边界 > 用户决定 > 系列简报与集纲 > 硬约束与门 > references 默认 > 风格/题材卡） |
| `references/look-development.md` | 何时值得做；三类代表帧（人物表现、核心地点、高压力场景）；每个方向写稳定项/可变量/叙事职责/失效信号；删掉风格名写法不变就是标签；风格参考的控制边界；接受的是可观察规则不是模型名 | **搬入** styles.md §1b。"展示给创作者选"改为导演岗自动决定并写决策记录；出代表帧只能用用户指定模型、计入已授权提交次数（硬约束 1b） |
| `references/pickup-and-alternate.md` | 母版/补拍/替代版的职责；补拍必须逐项交代原要求去向；补拍默认不替代母版 | **搬入** edit-and-delivery §2c（承担表；补拍＝shots.json 新增插入镜，替代＝逐项比过才在 review.json 选） |
| `references/production-form-profiles.md` | 形态卡是 craft_default；九项形态卡；异质身体物理卡；形态选择表；混合形态逐项声明；提示词构成随形态变的三条（身份载体、连续性必带、运动默认）；跨阶段传递表 | **搬入** styles.md §13（13.1 preset↔形态卡与身份载体、13.2 连续性必带/可省表、13.3 分层与运动默认与口型策略、13.5 混合形态与异质身体物理卡、13.6 各阶段多写什么）和 §11 第 9–10 问。九项卡片框架压缩进 13.1–13.3，没有逐项照抄 |
| `references/reference-roles.md` | 每张参考回答五问；九种用途与可控/不可控；身份与造型状态以"本集内会不会变"区分；道具板分身份/状态；没看过写未验证 | **重复** visual-assets §8（九用途、可控/不可控、负面词擦不掉像素）。"未验证"→ **搬入** project-hub §4。"本集内会不会变"的区分句 → 本 lane 不能写 visual-assets.md，**列为拿不准**（资产 lane 可能已从 short-drama-assets 搬入同义内容） |
| `references/runtime-preflight.md` | 定位项目；Windows 用 `py -3`；写入纪律（原子替换、外部编辑后先重读）；Dashboard 不承担授权 | 定位项目 → **重复** runtime-boundaries。先重读再改、保留稳定 ID → **搬入** project-hub §7。Windows `py -3` → **不搬**（drama-forge 目前在 macOS/Linux 使用，脚本统一 `python3`） |
| `references/form-cards/实拍.md` | 叙事职责；造型状态作身份锚点；逐镜必带（造型层次、湿污伤、手中物、光源、妆发衰减）；可控性分层；光写来源+方向+遮挡+反射；默认全动作、写限制；不把心理翻成症状；现场声源 | **搬入** styles.md §13.1（身份载体）、§13.2（实拍行）、§13.3（实拍运动）。光源写法 → **重复** styles §3–5 画面语言与 video-prompts-general §5 |
| `references/form-cards/二维动态漫.md` | 剪影+线条+色块锚点、剪影测试；阴影分区与描边连续性；四层拆分每镜点名；色块关系词汇；limited motion；口型策略；拟声字/心声框是合法载体 | **搬入** styles.md §13.1–13.3（剪影测试、阴影分区、可动层点名、limited motion、口型策略）。"拟声字、心声框由画面承载" → **不搬**：与硬约束 4（生成画面不出字）冲突，改为后期叠加 |
| `references/form-cards/风格化三维.md` | 比例+剪影+rig 边界；接触点、轴线、机位高度连续；混合层逐项声明；表面对光的响应；摄影机最贵、运镜要动机；接触即有声 | **搬入** styles.md §13.1–13.3、§13.5（接触点、重量结果、运镜动机、接触即有声→sfx、混合层） |
| `references/form-cards/水墨笔触.md` | 浓淡与留白的叙事职责；不可散边缘必须点名；墨六项表；着彩只给一个焦点；极低运动预算；旁白说画面没画的；题款竖排字是合法载体 | **搬入** styles.md §13.4（新增水墨写法、墨六项表、不可洇化边缘、风格句与视频保持句参考）。题款竖排字画进画面 → **不搬**（与硬约束 4 冲突，改后期叠加）。旁白为主 → 改写为不替代角色开口（台词多的预设）。drama-forge 没有水墨 preset → 借 `anime_cel` + 决策记录，正式新增 preset 需改脚本，**列为拿不准** |
| `references/form-cards/Q版表达.md` | 比例体系+色块+放大记号；一镜一因果；符号层（问号汗滴箭头）不能替代事实；旁白说规则画面说后果；安全边界；可爱不等于持续弹跳 | **搬入** styles.md §13.4（Q 版写法、风格句参考）。符号层画进画面 → **不搬**（硬约束 4，改后期叠加或无字图形）。"旁白说规则" → 与"能力说出来"不冲突但主体不同，改写为规则由角色台词或字幕明说。借 `anime_cel` preset（同上，拿不准） |
| `references/form-cards/国漫二次元.md` | 精修画风人物趋同是头号风险；逐条枚举结构差异到两两可分；氛围色不吃识别色；背景写实度差档要声明；全动作预算给情绪转折镜；缓推要写职责 | 结构差异、氛围色、差档 → **部分重复** styles.md §6–8 各节（[套件] 标注的条目）。**搬入** §13.1 身份载体（枚举到两两可分）、§13.2 精修行、§13.3 精修运动（全动作预算、缓推职责） |
| `scripts/project_tool.py` | init/status/publish/accept/review/set-authority/package/verify/export | init/status → **重复** drama-forge `project_tool.py`。export → **搬入** `hub_tool.py export`。publish/accept/review/set-authority/package/verify → **不搬**（逐项人确认与审批包，和全自动流程冲突） |
| `scripts/dashboard_server.py` | 仅本机回环的 HTTP 服务、会话令牌、原子写、detach 常驻、status/stop | **不搬**（见 dashboard 行）；只读进度页由 `hub_tool.py overview --html` 生成静态文件，不起服务、不开端口 |
| `scripts/creator_markdown_check.py` | 五文档跨文档结构校验（IMG/REF/PLAN 语法、视觉依据覆盖、画面代称、连续性锁面携带、台词引号可在剧本找到、未拍场次） | **重复** shots_tool.py 的机械门（G23 锁面携带、G09/G10 台词逐字、G18–G20 参考图、G41 cut_order 等）；五文档专有语法 → **不搬** |
| `scripts/selftest.py` | 总控套件自测（init、publish/accept、Dashboard、export） | **不搬**原测试；export/overview 的测试写成 `merged_selftest.py::test_hub_tool` |
| `scripts/__pycache__/project_tool.cpython-313.pyc` | 字节码缓存 | **不搬**：编译产物 |

## 拿不准的取舍（交主会话定）

1. **水墨、Q 版没有 preset 值**：styles.md §13.4 让它们借 `anime_cel`、整句换风格句并写决策记录。要正式成为第八、九个 preset，需要改 `shots_tool.py` 的 G33 和 `project_tool.py init --style-preset` 可选值（不在本 lane 可写范围）。
2. **audience-reveal 的两句独有内容**（"认识主角"与"是谁"分开扣；每条隐藏信息写保护方法）没有落进 scene-state-and-reveal.md（不在本 lane 可写范围），建议主会话补一句。
3. **reference-roles 的"身份 vs 造型状态按本集内会不会变区分"** 没落进 visual-assets.md（不在本 lane 可写范围），请与资产 lane 的台账核对是否已搬。
4. **Dashboard 判为不值得移植**，只做了只读 HTML 快照；如果用户确实想要网页里编辑，需要另开任务针对 drama.json/shots.json 结构重写（编辑 shots.json 而不是渲染出的 md）。
5. `hub_tool.py grade` 的镜头边界来自 cut.py 剪辑单"时长"列（两位小数）累加，与实际编码帧边界可能差 1 帧；校正区间末端已收 1 ms；只在合成片上测过（merged_selftest），没有在真实长片上验证累积误差，用前看一眼 `_graded` 版剪辑点附近。
