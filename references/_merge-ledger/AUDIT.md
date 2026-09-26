# 合并独立核对报告（AUDIT）

- 核对日期：2026-09-26
- 核对人：独立核对员（没参与合并），只读核对，只写本文件。
- 范围：`.claude/skills/short-drama*` 共 11 个子 skill → `.claude/skills/drama-forge`。

## 结论：SAFE-TO-DELETE（原结论为 GAPS；第 6 节列的 5 个缺口已于 2026-09-26 全部补完，落点见文末第 7 节"缺口已补"）

绝大部分内容已进入 drama-forge：台账覆盖了全部文件；抽检 60 多个独有概念，几乎都能在正文里找到对应内容；运行时代码不依赖子 skill；5 套 selftest 全部通过。唯一真正会随删除丢失的内容是配音表的四个上下文字段（缺口 1）。缺口 2 属于规则只在文字里提到、没有落到检查项。其余 3 条不阻断删除。

## 1. 文件去向覆盖

用脚本逐个列出 11 个子 skill 的全部文件（`.DS_Store`、`__pycache__` 除外），再到 `_merge-ledger/*.md` 里对应的 `## short-drama-xxx` 小节查找相对路径。

| 子 skill | 文件数 | 台账有记录 | 缺记录 |
|---|---|---|---|
| short-drama（总控） | 30 | 30 | 0 |
| short-drama-assets | 24 | 23 | 0（另 1 个是 `references/.omc/state/.../pre-tool-advisory-throttle.json`，属于 OMC 运行时残留，不是内容） |
| short-drama-develop | 36 | 36 | 0 |
| short-drama-edit | 20 | 20 | 0 |
| short-drama-image-prompts | 20 | 20 | 0 |
| short-drama-novel-analyze | 11 | 11 | 0 |
| short-drama-produce | 14 | 14 | 0 |
| short-drama-review | 19 | 19 | 0 |
| short-drama-storyboard | 24 | 24 | 0 |
| short-drama-video-prompts | 28 | 27 | 0（同上，另 1 个 `.omc` 残留） |
| short-drama-write | 22 | 22 | 0（`assets/episode-card-standalone.json` 和 `episode-card.json` 合在同一行登记） |

结论：没有文件缺去向记录。两个 `.omc/state` 残留文件删除时一起删就行。

## 2. 抽检（每个子 skill 至少 5 项）

判定：已覆盖 = 在 drama-forge 正文里找到对应做法（不要求逐字相同）；部分 = 有相关内容但少了关键一块；缺失 = 找不到。

### short-drama-develop（重点：人物记忆、多季、题材卡、分集、机制循环）
| 概念（来源） | drama-forge 位置 | 判定 |
|---|---|---|
| 前史储备 + 叙事切入窗口（serial-character-and-memory §2） | series-long-form §1–2 | 已覆盖 |
| 驱动力七层、压力测试、双轨节奏（同上 §3、§4、§7） | series-long-form §1–4、story-engine | 已覆盖 |
| 可恢复的跨集记忆 + 绝不能无原因重置的事实（同上 §8） | series-long-form §5、`assets/templates/跨集记忆.md` §1–8 | 已覆盖（见缺口 3：位置表述不一致） |
| 多季、续季、跨季线（serial / genre-cards 前中后期） | series-long-form §6、review-checklists §S、仙侠卡"续季"段 | 已覆盖 |
| 机制循环：一次运行 vs 重复、耗尽、三种处置、换代紧迫性、落差型循环（mechanism-loop） | story-engine §9 | 已覆盖 |
| 先知型 / 授权型装置、宣告是一次披露（premise-devices） | story-engine §4 | 已覆盖 |
| 公平揭示五问、有因果的反转句式、承诺重心表（reveal-reversal-payoff） | story-engine §3、§8"揭示与反转" | 已覆盖 |
| 避免机械轮换：相邻集五项比较（reveal-reversal-payoff §6） | story-engine §3 升级四运动"相邻集尽量不同"、§6 兑现子模式轮换 | 部分（五项比较清单没单列，见缺口 5） |
| 单集契约 / 出去压力 / 门槛集 / 容量预算（episode-design） | series-long-form §8 分集卡、story-engine §5 | 已覆盖 |
| 12 张题材卡 + 索引（genre-cards） | `references/genre-cards/` 12 张卡 + `索引.md` | 已覆盖；逐张核了核心句（复仇打脸"权力位置可核对的变化""不完整的偿还"、身份错位"同一形象 + 行为差异"、破镜重圆"谁误会了谁"三支） |
| 仙侠修真卡（重点） | genre-cards/仙侠修真.md | 已覆盖且有增补：原卡的核心、压力、策略、兑现、场面颗粒、钩子、前中后期、制作难点、禁止漂移全在；另加了市场节拍、续季切法、画风、好拍/难拍、禁区 |
| 多集整稿接入：原字节、只读当前切片、断点续跑（multi-episode-intake） | adaptation §5.1–5.4 | 已覆盖 |
| 对标材料只学机制、must_not_copy（creative-reference-intake） | adaptation §8 | 已覆盖 |
| 导演阐述"跨集阶段的镜头语言职责"（director-brief-craft） | 没搬（台账 story.md"拿不准"第 6 条有意放弃） | 缺失（有意放弃，见缺口 4） |

### short-drama-novel-analyze（重点：小说改编与原著分析）
| 概念 | 位置 | 判定 |
|---|---|---|
| 章节索引唯一切片真源、中文数字、按卷校验（novel_index.py） | `scripts/novel_index.py`（已迁入）、adaptation §4.1 | 已覆盖 |
| 改编价值快评六件事、首尾必取等距抽样、开篇替换点 | adaptation §4.2 | 已覆盖 |
| 逐章提取格式、白描 / 叙事框架词对照、密度、grep 自检 | adaptation §4.3 | 已覆盖 |
| 剧情单元粒度、覆盖率阈值 85–95%、散落兜底 | adaptation §4.4 | 已覆盖 |
| 人物归并、设定归纳 | adaptation §4.5 | 已覆盖 |
| 三类判定（能直接拍 / 要换载体 / 只能靠文字）、桥段标签、分集候选、回填快评 | adaptation §4.6 | 已覆盖 |

### short-drama-write
| 概念 | 位置 | 判定 |
|---|---|---|
| 制作稿格式【】△▲ 的识别与规范化（production-format-dialect） | screenplay §1b + `screenplay_lint.py` SP06 | 已覆盖 |
| 声音戏剧五问（scene-sound-dramaturgy） | screenplay §5c | 已覆盖 |
| 长单集分批续写的交接摘要（scene-handoff-capsule） | screenplay §9"长单集分批续写" | 已覆盖 |
| 可替代实现（substitutable-realization） | screenplay §7c、review-checklists | 已覆盖 |
| 对白议程、权力、打断（dialogue-craft） | screenplay §4d | 已覆盖 |
| 配音表上下文字段 addressed_to / preceding_line / speaker_knows_now / tactic（voice-record-sheet.jsonl.md） | production-and-review §10 没有 | 缺失（缺口 1） |

### short-drama-review（重点：审查量表）
| 概念 | 位置 | 判定 |
|---|---|---|
| 严重度与结论 PASS/REVISE/BLOCKED | review-checklists §0.2–0.3、`review_md_check.py` | 已覆盖 |
| 去模板感诊断四层（anti-template-repair） | review-checklists §0.7 | 已覆盖 |
| 故事与剧本量表（rubric-story-script） | review-checklists §A–C | 已覆盖 |
| 资产与提示词、视觉与运动量表（rubric-assets-prompts / visual-motion） | review-checklists §D–E | 已覆盖 |
| 原著分析量表（rubric-source-analysis） | review-checklists §R、§R2 | 已覆盖 |
| 项目校准：观察 → 诊断 → 单变量修订（project-calibration） | review-checklists §F–J | 已覆盖 |

### short-drama-assets
| 概念 | 位置 | 判定 |
|---|---|---|
| 出现方式四类、布景、群体称谓、含混指代（occurrence-extraction） | visual-assets §1b | 已覆盖 |
| 身份 / 变体 / 镜头瞬态 / 故事语义四分 | visual-assets §2、§2b | 已覆盖 |
| 地点与视图、光与陈设要有来源（location-and-view） | visual-assets §4c | 已覆盖 |
| 连续性变化记录五组状态、非线性时间、修订影响（continuity-delta） | visual-assets §6c | 已覆盖 |
| 锁面写法（continuity-lock） | visual-assets §6b、G23 | 已覆盖 |
| 声音方向与音色身份（voice-direction） | visual-assets §3d、视觉设定模板"声音方向" | 已覆盖 |
| CON-07：锁面要逐字进范围内的关键帧**和视频提示词** | 关键帧有 G23；视频提示词只在 video-prompts-general §2 提到"保留连续性锁"，没有检查项 | 部分（缺口 2） |

### short-drama-image-prompts（含 look development）
| 概念 | 位置 | 判定 |
|---|---|---|
| 转面板只作目检和裁格，不直接挂首帧（production-sheet-recipes） | image-prompts §3.3、`visual_lint.py` V01、pipeline-contract `layout: multi_view` / `crop_from` | 已覆盖 |
| 造型与状态变体（look-and-state-variant） | image-prompts §3.4 | 已覆盖 |
| 底板、道具图（location-plate / prop-plate） | image-prompts §3.5–3.6 | 已覆盖 |
| 局部编辑与重出（edit-and-revision） | image-prompts §4 | 已覆盖 |
| 风格帧 / Lookdev 三类测试轴（lookdev-frame） | image-prompts §3.7、styles §1b | 已覆盖 |
| 按"要比较什么"选布光 | image-prompts §5 | 已覆盖 |
| 8 维证据量表、反例 A/B/C（review-and-fixtures） | image-prompts §9 | 已覆盖 |

### short-drama-storyboard
| 概念 | 位置 | 判定 |
|---|---|---|
| 关键场次导演方案比较五种命题（coverage-audition） | storyboard-keyframes §2d | 已覆盖 |
| 复杂调度：竖屏多人、单房对白、证据揭示、群体、动态对象（blocking-playbooks） | storyboard-keyframes §9b | 已覆盖 |
| 漫剧关键帧三层：事实 → 画风投影 → 可读性（comic-keyframe-lexicon） | storyboard-keyframes §6d | 已覆盖 |
| 镜头 ID 修订规则（shot-revision-identity） | storyboard-keyframes §10b | 已覆盖 |
| 景别词表、机位三栏（production-shot-grammar） | storyboard-keyframes §7d | 已覆盖 |
| 布光按镜头职责（lighting-craft） | storyboard-keyframes §6b 第 7 项、§8 | 已覆盖 |

### short-drama-video-prompts（重点：Seedance 方言）
| 概念 | 位置 | 判定 |
|---|---|---|
| Seedance 2.0 / 2.5 差异、时间段写法、4–15 / 4–30 秒 | video-prompts-seedance §2–4、§6 | 已覆盖 |
| 2.5 任务类型 reference / edit / extend 及接口硬条件（ratio adaptive、duration -1） | video-prompts-seedance §4、`seedance_task` 字段 | 已覆盖 |
| 从上一段实际结果续接、`continuation_pending` | video-prompts-seedance §5 | 已覆盖 |
| 音色参考不能只凭正文声称已绑定 | video-prompts-seedance §4 | 已覆盖 |
| 表演五步、动作时序与分段算术（performance-action-timing） | video-prompts-general §4–5 | 已覆盖 |
| 可生成性、交付文本只含要拍的内容（generability / delivery-profile） | video-prompts-general §9b、production-and-review | 已覆盖 |
| 配乐规格（music-spec） | providers.md §5、video-prompts-general §9 | 已覆盖 |

### short-drama-produce（重点：生产通道适配器与收回规则）
| 概念 | 位置 | 判定 |
|---|---|---|
| 任务号先落盘、中断不等于重跑、reconcile 收回 | providers.md、runtime-boundaries、`h3_client.py` / `providers.py` | 已覆盖 |
| 5xx 按"提交结果未知"`submission_unknown` 处理 | providers.md、`providers.py`、merged_selftest | 已覆盖（比原套件更保守） |
| 参考约束追加（role / may / must） | `providers.py` `with_reference_contract` | 已覆盖 |
| MiniMax H3：7000 字符、ratio、首尾帧与参考互斥 | providers.md §2 | 已覆盖 |
| MiniMax 语音：language_boost 不用 auto、情绪白名单、pronunciation | providers.md §4、production-and-review §10 | 已覆盖 |
| gpt-image-2（不传 input_fidelity）、minimax music-3.0（纯配乐 / 歌词） | providers.md §5–6 | 已覆盖 |
| 错误里不带响应正文、凭据只从环境 | `providers.py` ProviderError | 已覆盖 |

### short-drama-edit（重点：剪辑规格）
| 概念 | 位置 | 判定 |
|---|---|---|
| 先看完整素材标可用带 | edit-and-delivery §1b | 已覆盖 |
| 保声换画（`audio_from`） | edit-and-delivery §1b | 已覆盖 |
| 响度与真峰实测（−1 dBTP、两遍 loudnorm 会退回动态处理、48 kHz） | edit-and-delivery §5 | 已覆盖 |
| 接镜色彩与颗粒 | edit-and-delivery §5b、`hub_tool.py measure/grade` | 已覆盖 |
| 补拍与替代 take 的职责承担表（pickup-and-alternate，来自总控） | edit-and-delivery §2c | 已覆盖 |
| 竖屏字幕安全区、字幕逐字取剧本 | edit-and-delivery §3–4 | 已覆盖 |
| Remotion 字幕路线 | 有意不搬（PIL + overlay 已能做） | 有意放弃，合理 |

### short-drama（总控，重点：look development、制作形态）
| 概念 | 位置 | 判定 |
|---|---|---|
| Look Development 三类代表帧、稳定项 / 可变量 / 失效信号 | styles §1b | 已覆盖 |
| 六张制作形态卡（实拍、二维动态漫、国漫二次元、风格化三维、水墨、Q 版）、异质身体、混合形态 | styles §13.1–13.6 | 已覆盖 |
| 观众揭示："来者认识主角"和"来者是谁"分开扣、保护方法 | scene-state-and-reveal"三本账" | 已覆盖 |
| 身份与造型状态按"本集之内会不会变"区分 | visual-assets §8 | 已覆盖 |
| 冲突优先级、决策记录类别、观察六项 | project-hub §4–6 | 已覆盖 |
| export 快照、只读进度页 | `hub_tool.py export` / `overview --html` | 已覆盖 |

## 3. 对 short-drama* 的残留依赖

- `drama-forge/scripts/*.py`：没有任何 import、subprocess 或路径指向 `short-drama*`。唯一命中是 `common.py` 的 schema 常量 `short-drama-autopilot/{shots,drama,refs}/v1`，以及模板和示例 json 里的同名 schema，属于允许保留的数据 schema 常量。
- `drama-forge` 的 md 文件：没有指向 `short-drama*` 目录的 Markdown 链接。剩下的只是文字说明：各题材卡、story-engine、series-long-form、adaptation 末尾的"合并自原 short-drama-xxx"，README 的来源致谢，SKILL.md / runtime-boundaries 对旧 `short-drama.json` 项目的说明，以及外部 URL（0xsline/short-drama、screenweaver 等）。删掉子 skill 后这些都不会失效。
- 台账里列的残留指向（SKILL.md"深挖时读的本地套件"、styles.md 旧第 315 行、market-hits 两处）都已经清掉，复查没有命中。
- 项目仓库其他位置（`CLAUDE.md`、`README.md`、`交接.md`、`脚本/`、各剧 `项目开发/`）也没有引用子 skill 路径。

## 4. 与 drama-forge 硬规则的冲突检查

各 lane 台账都列了冲突处理方式（倒叙和结果预演改成顺叙、屏显文字改成后期叠加、群像改成具名单人镜、VO 放到最后、逐步确认改成自动决策加决策记录、生产确认闸门改成批次授权）。抽查结果：

- "等创作者确认 / 接受"一类表述已经清掉；剩下的只在 project-hub §5 用来说明"原套件如此，这里已改"，以及 adaptation §4.2 的"替代停下问用户"。
- 生成画面里出现拟声字、心声框、题款的写法：styles 里都明确写成"不让模型画、后期叠加"，没有照搬。
- 台账 write-review 提到的 screenplay §2"严格按时间顺序"和 SKILL 6b 口径不一致：现在的 screenplay 已经没有这句，§1b 第 4 条按 6b 处理。已统一。
- 生活流"hold pose 留白"、"不规定第几秒"：题材卡已改成"不低于节奏下限、要过 B1"。
- 一处轻微不一致（不冲突）：review-checklists §0.2 仍然用原套件的四级分类（structural_invariant 等）来对照严重度，而台账说"不搬分级体系"。这只是用来对照，不形成第二套门，可以保留。

没有发现合并进来的内容和硬规则直接冲突。

已知的限制（不是合并缺口，删除子 skill 也不影响）：`shots_tool.py` 的 G09/G10/G17/G44 还不认 Seedance 的花括号台词，`produce.py` 只对接 H3（video-prompts-seedance §7 已写明）；`common.py::parse_screenplay` 会把注释和冒号动作行误读成对白（write-review 台账已记，由 screenplay_lint 拦截）。

## 5. selftest（本次亲自跑）

| 命令 | 结果 |
|---|---|
| `python3 scripts/selftest.py` | exit 0，24 self-tests passed |
| `python3 scripts/merged_selftest.py` | exit 0，7/7 passed（hub_tool、video_produce_providers、visual_lint、screenplay_lint、review_md_check、novel_index、episode_intake）；输出里的 "1 errors, 7 warnings" 是 visual_lint 夹具的预期输出 |
| `python3 scripts/quality_selftest.py` | exit 0，Ran 29 tests OK |
| `python3 scripts/client_selftest.py` | exit 0，Ran 19 tests OK |
| `python3 scripts/selftest_providers.py` | exit 0，test_video_produce_providers ok |

## 6. 缺口清单

| # | 严重度 | 来源文件 | 缺什么 | 建议并到哪 |
|---|---|---|---|---|
| 1 | 删除前补 | `short-drama-write/assets/voice-record-sheet.jsonl.md` | 配音表的四个上下文字段和理由：对谁说（addressed_to）、上一句是谁说的（preceding_line_id）、说话人此刻知道什么（speaker_knows_now，"同一句在知道和不知道时是两种读法，是最常见的重录原因"）、这句的策略（tactic，"情绪词不可执行，策略可执行"）。write-review 台账写了"建议并入"，总装补记里没有处理，删除后这部分内容会丢。 | `references/production-and-review.md` §10 "生成"部分加一条：送 TTS 或交配音前，每句在配音表里写这四项；可选落到 `shots.json` 的 `dialogue[]`（例如 `to` / `knows` / `tactic`），剧本仍然是台词的唯一来源 |
| 2 | 删除前补（一句话） | `short-drama-assets/references/stage-contract.md` 与 `short-drama-video-prompts/references/stage-contract.md` 的 CON-07 | 锁面逐字进范围内的**视频提示词**。现在只有关键帧由 G23 机械检查；视频提示词只在 video-prompts-general §2 顺带提到"保留连续性锁"，review-checklists §E4 / §E5 没有对应问题 | review-checklists §E5 加一问："范围内每镜的视频提示词是否逐字带了 `locks[].phrase`？"；以后可以把 G23 扩到 `prompt` 字段（改 shots_tool.py，属于可选增强） |
| 3 | 不阻断 | `short-drama-develop/assets/story-engine.md`、`serial-character-and-memory.md` §8 | 内容已搬，但位置说法不一致：series-long-form §5 说"绝不能无原因重置的事实"列在**系列简报**里，实际模板放在 `跨集记忆.md` §8；续季的 `## 季规划`、机制差异表也没有进 `系列简报.md` 模板（story 台账"拿不准"第 4 条） | 把 series-long-form §5 那句改成指向 `跨集记忆.md` §8；需要的话给 `系列简报.md` 加 `## 季规划` 节（注意 project_tool 解析 `## 立项候选` 表，别动那张表） |
| 4 | 不阻断（有意放弃） | `short-drama-develop/references/director-brief-craft.md` | "跨集阶段 + 镜头语言职责"：不同阶段的镜头语言怎么变。台账认为它和节奏下限、长镜头合并、styles 锁定重复，所以没搬 | 如果想保留，在 storyboard-keyframes 或 series-long-form §6 加 2–3 行（例如"前期多用客观中景建立规则，后期用主观近景承接代价"），否则接受放弃 |
| 5 | 不阻断 | `short-drama-develop/references/reveal-reversal-payoff.md` §6 | "避免机械轮换"的相邻集五项比较（压力来源是否学习、主角策略是否改变、代价落在哪种价值、观众得到哪类回报、制作负担）。story-engine 有"相邻集运动尽量不同"和兑现子模式轮换，但没有这张清单 | story-engine §6 或 review-checklists §B 加一问，列这五项 |

补完第 1、2 条（各几行文字）以后，可以按 SAFE-TO-DELETE 删除 11 个子 skill，删除时连同两个 `.omc/state` 残留目录一起删。

## 7. 缺口已补（2026-09-26）

补缺口的人只改了 drama-forge，没有改 `short-drama*`，没有做 git 操作。

| # | 落点 | 做了什么 |
|---|---|---|
| 1 | `references/production-and-review.md` §10"生成"新增"每句带上下文四项"；`references/pipeline-contract.md` §4 `dialogue[]` 示例注释 | 用自己的话写了对谁说、上一句是谁说的、说话人此刻知道什么、这句的策略四项和各自理由（集中录制丢上下文；知道与不知道是两种读法，最常见的重录原因；情绪词演不出、策略演得出）；写明配音表是剧本的投影、对不上时以剧本为准；可选落到 `dialogue[]` 的 `to` / `knows` / `tactic`，上一句由镜序推出不另存，门不检查 |
| 2 | `references/review-checklists.md` §E5 第 10 问；`scripts/shots_tool.py` G23；`scripts/selftest.py`；`assets/example/EP001/shots.json`；`references/pipeline-contract.md` G23 行 | §E5 加问"范围内每镜的 video_prompt / video_body 是否逐字带 `locks[].phrase`"。G23 扩到视频提示词：剥掉 `<d>…</d>` 台词后查 `video_prompt`（没有就查 `video_body`），否定式不算，报 warn（起始帧缺锁面仍是 error），`waive` 可豁免。示例 S01、S04 的视频提示词补了锁面 `charcoal grey blazer`。selftest 加两条断言：示例不报 G23 warn；删掉 S01 视频提示词里的锁面要报 G23 warn 且不升 error |
| 3 | `references/series-long-form.md` §5 末段、§6.1；`assets/templates/系列简报.md` 新增 `## 季规划` | §5 的"绝不能无原因重置的事实"改为指向 `assets/templates/跨集记忆.md` §8（没建跨集记忆的 6 集单季项目在系列简报末尾加同名清单）。系列简报模板在"分集走向"和"视觉方向"之间加 `## 季规划` 表：季、大循环、境界 / 地图、主要对手、机制的新限制、季末大兑现、明线 / 暗线各一格、续季钩子；§6.1 的表头同步成同一套列并指向模板。`## 立项候选` 表没动 |
| 4 | `references/series-long-form.md` 新增 §6.4b"跨集阶段的镜头语言职责" | 两三句：按人物选择 / 关系 / 信息权限的门槛分阶段、每阶段写一句镜头语言职责（例：规则建立期客观中景，代价累积期主观近景和反应镜），手持、平行蒙太奇等只在承担具体节点职责时用；写明节奏下限（§7c、G42）和同一人连续戏合并长镜头（§7b、G45）照常生效 |
| 5 | `references/review-checklists.md` §B 第 12 问 | "不机械轮换"一问五项：压力来源是否学习、主角策略是否改变、代价落在哪种价值、观众得到哪类回报（信息 / 关系 / 能力 / 情绪）、空间 / 资产 / 制作负担是否还扛得住；五项都和上一集一样就记为问题 |

复测（补完后亲自跑）：

| 命令 | 结果 |
|---|---|
| `python3 scripts/selftest.py` | exit 0，24 self-tests passed（含新增 G23 视频提示词断言） |
| `python3 scripts/merged_selftest.py` | exit 0，7/7 passed（"1 errors, 7 warnings" 仍是 visual_lint 夹具的预期输出） |
| `python3 scripts/quality_selftest.py` | exit 0，Ran 29 tests OK |
| `python3 scripts/client_selftest.py` | exit 0，Ran 19 tests OK |
| `python3 scripts/selftest_providers.py` | exit 0，test_video_produce_providers ok |
| drama-forge 全部 .md 的相对链接 | 164 条，0 条断链 |

结论：5 个缺口都已补完，可以 SAFE-TO-DELETE 11 个 `short-drama*` 子 skill，删除时连同两个 `.omc/state` 残留目录一起删。
