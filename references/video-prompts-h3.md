# 视频提示词：MiniMax H3 方言 + 表演与对白层

阶段 E 写 `shots.json` 的 `video_prompt`（或 `video_body` + `soundscape`，由 `shots_tool.py build` 拼骨架）时读本文件。来源：本地视频提示词套件（H3 方言、生产语法、运动配方、表演与时序、可生成性、摄影与声音连续性，已合并进本技能）、cinematic-video-prompt-engineer 的表演/对白/运镜库、shuohao 的 H3 结构对账，以及实战项目通过审查的写法。

本文只管项目 H3 适配语法。内容原则见 [video-prompts-general.md](video-prompts-general.md)：必要状态变化、可读接触、按需环境运动、逐 take 实测；不要求固定节拍或每镜背景动态。接口能力以当前适配配置和已验证请求为准。

## 目录

1. H3 三段骨架与硬规则
2. 说话对象入画与口型
3. 台词多、反应快
4. 正文怎么写：起点 → 唯一动作 → 台词挂拍 → 终点
   4b. 环境动态在 H3 里的写法
5. 表演层：触发词、两个信号、情绪保护层
6. 运镜：5 秒人物镜常用八种
7. 可生成性改写阶梯
8. 听者镜与反应优先
9. 实战骨架与示例
10. 自检清单
11. 参考模式：首尾帧、六段 full-reference、素材上限与续接

## 1. H3 三段骨架与硬规则

```text
integrated_multimodal_description: [Shot 1] <头部固定句> <起点> <唯一动作> <台词事件> <终点>
overall_soundscape: <环境声 / 音效 / 非语言人声；不重复对白；末尾写 These are the only sounds in the shot.>
non_diegetic_music: N/A
```

- `duration` 是 4–15 的**整数秒**，由 `shots.json` 的 `seconds` 决定；正文里的秒数不能代替请求时长。
- 起始帧图生视频走 `first_frame`（`image_mode: keyframe`），三段结构；起始帧只锚定开场构图与姿态，不锁整镜画面语法。起始帧和参考图/参考音频**互斥**，要挂身份图就整组走六段 full-reference（自建 API 是否支持要先验证；现阶段默认三段）。
- 结构字段用英文；台词写 `<d>[Japanese] 逐字台词</d>`，`<d>` 里只放语言标签和台词原文，秒数、声线、语速写在外面；每句只出现一次，紧跟在说话人的可见动作句后；不加剧本外的前导句；`<d>` 里的省略号「……」改成逗号或删掉（字幕仍按剧本，E31）。
- 说话人稳定 ID `(S1)`：第一次出现时在 `<d>` 外交代画内/画外和音色；同一角色全剧用同一段音色描述（写在 refs.json 的 `voice`，G21 对账），这是首帧模式下减少逐镜音色漂移的唯一办法。
- `non_diegetic_music: N/A` 必须显式写；省略这一层小样本里出现过额外配乐。配乐在剪辑层加。
- 无对白镜写 `He says nothing. No one speaks, laughs, shouts or cries out.`，否则模型会自编人声（笑声、冷哼 ASR 抓不到，按 video-prompts-general §2b 声音一行验收）（审片时 ASR 会抓）；有对白镜在最后一句 `<d>` 后写唯一台词句（video-prompts-general §2b 表的声音一行）。
- 正文 ≤ 7000 字符，除此之外不设字数目标；video-prompts-general §2b 的封闭清单一项不能少，清单外只写本镜变化需要的内容。
- **正面描述、不留分支**：`不要进红框` → `直接进蓝框`；不出现 `or / 或 / 二选一 / 可选`（G22）。否定式动作改写成可见动作；点名否定的唯一例外见 video-prompts-general §2b。
- **交付文本只含要拍的内容**：不写文件名、ID、规则号、重投备注、无关否定罗列。"锁定参考图" → "衣着与起点一致"。
- 方向优先用画面里的实物做参照（朝门、背对洗手台），不写 left/right（video-prompts-general §2b 三）；非写不可时写 `screen-left` 并在同一句写人物朝向；人物自身的左右带主体（"his left hand"）。
- 摄影机一栏不能空着：锁定也要写（景别 + 机位高度 + 保持多久），空着会被读成可以自由漂移。
- 声景是动作指令：声景里写了撞击，画面就会演出撞击。同场相邻镜底声写成一致，否则切点会"呼"一声换空间。

## 2. 说话对象入画与口型

本地实测：近处骑手正脸不说话时，旧写法 3 次里 2 次把口型放到骑手脸上；补"骑手不说话、嘴唇紧闭"后 3/3 正确；骑手出画或背身 12/12 正确。**模型把口型放到画面里最显眼的正脸上。**所以：

- 台词镜按 storyboard-keyframes §1：被说话的人必须入画（两人一左一右，或听者背影在前景），人数写 `exactly N`、每人一次（video-prompts-general §2b）；单人台词镜只限 §1 的例外并写 `single_reason`。口型会落到最显眼的正脸上，所以听者优先背对镜头（`seen from behind, his face never turns toward the camera`），并写明全程只有谁开口。
- 画内有第二张看得见的脸（听者正脸、接触同框）：`<Other> does not speak; his lips remain completely closed for the whole shot.`
- 画外台词（`[OS]`）：**H3 不会生成画外人声**（实测三个 take 都没声音）。画外说的话要么改成说话人在镜的台词镜（听者照样入画），要么另生成一个该人物当面说这句的音源镜（不进 `cut_order`），在听者镜上用 `audio_from` 垫音；听者镜正文写 `No one speaks`、嘴唇闭合。小声台词写成低声但每个字清楚、嘴唇可见，不写耳语（耳语会没声）。

## 3. 台词多、反应快

项目口味，已经写进门：

- 人物镜默认有一句台词；项目为 `commercial_fast` 或决策记录写明快反应时，第一句在 1 秒内开口（G05）；其他项目的开口时机跟触发走（video-prompts-general §4）。反应类台词写 `At the same instant` / `at about a quarter of a second`；被抢、被打、被戳穿当场出声。
- 对白预算：`发声窗口 = 镜长 − 开口前等待 − 不能并行的动作 − 其他人发声 − 末尾落点(0.5–1.0s)`。5 秒镜约 3.8 秒发声，中文约 15 字（H3 实测 4.1 字/秒），日语按 `speech_rates.ja` 估、用首批 ASR 实测校准（G04 用它算容量）。
- 放不下时的降负载顺序（不许加速、截断、静默删字）：删装饰性运镜 → 删次要手势和环境小动作 → 加秒数（H3 到 15 秒，上限 `shot_seconds.max`；同一个人连说两句就写成一个长镜头，video-prompts-general §3b） → 让台词跨到反应镜（剪辑层 L/J-cut） → 换人说话才拆镜。台词只能回剧本阶段改。
- **台词语种**：`<d>[Japanese]` 的语种标签必须等于 `drama.json` 的 `dialogue_lang`（ja→Japanese、zh→Chinese、en→English、ko→Korean），`<d>` 外的说话方式也写同一种语言（`says in Japanese`）；标签写错，H3 会用别的语言的口音和语调去念（G44）。
- **视线**：说话人 `<d>` 前后写清看谁、看哪一侧（`keeping her eyes on the man off screen-left`），和 shots.json 的 `gaze` 一致（G43）；不写 looks at the camera。
- 抢话只在同一次生成内成立：写清入场触发词、谁让位、被打断者嘴停在哪；跨镜抢话放到剪辑层。

## 4. 正文怎么写

节拍链：`从<最少起点>开始。首先<起手>；接着<动作、方向、幅度>；随后<结果>；与此同时<另一通道：呼吸/视线/手>；最终<终点>。摄影机<锁定或移动及其目的>。台词挂在它发生的那一拍。`

七项检查：起手｜串行链带方向幅度｜至少一处量级（约半步、约一掌、约三十度）｜一条并行通道｜结束状态｜摄影机及其目的｜台词挂拍。

- 起点 = 起始帧的可见姿态，不复述静态外观（衣服、脸、背景由起始帧承担）。
- 一镜一个主导变化、一个主运镜；上一镜已完成的推近或动作不在下一镜重来；每镜结束形成新状态，终点 = `end_state`，下一镜从它接。
- 显式分段时，各段并集必须正好等于镜长；余量会被模型用无来源动作填满。
- 生成优先级梯（指令冲突时先简化低优先级项）：台词顺序、说话者身份、口型 > 听者反应 > 连续手势与视线 > 镜头装饰与环境细节。

## 4b. 环境动态在 H3 里的写法

规则见 video-prompts-general.md §6：仅在自然存在或有叙事作用时添加环境运动；G35 只查已声明必需的描述。

- 仅在环境确有变化且影响本镜时写具体变化；head 中的人物呼吸/眨眼无需用额外背景动态补齐。
- 背景人只在本场在场名单里有群演时才写，写明人数和位置（`two students far down the corridor on screen-right`）并写 `does not speak`，防 H3 冒人声或把口型挂到他身上；名单里没有群演的场写 `the corridor is otherwise empty`。说话对象不能写成背景路人来绕过人数；背景人不写 `in focus`（G13）。
- 环境动态和 `overall_soundscape` 对上：写了"远处走过的学生"，声景就有远处的脚步和人声；写了"空调风"，声景有空调声。

## 5. 表演层

**台词的情绪写进说话方式**：`dialogue[].emotion`（情绪·强度·语速·音量，screenplay §4b）要翻成 `<d>` 前面那句的说话方式，例 `惊慌·强·快·大` → `shouts in a panicked, breathless voice`；`冷笑·中·慢·小` → `says slowly and quietly, with cold contempt`。只写 `says` 就会得到平读。

表情词不单独写 `smirk`、`grin`、`sneer`，改写成肌肉与肢体动作（改写表见 video-prompts-general §5）。

**压缩版表情时间轴**（5 秒镜只留三样）：触发词 + 一个面部或身体变化 + 说后余态。

```text
At about half a second the man (S2), on-screen, with a smooth condescending voice, says in Japanese: <d>[Japanese] 君がいなくても、回るよ。</d>
On 「回るよ」 one hand opens outward in a small shrug; after the line one corner of his mouth stays pulled up, eyes cold, not a warm smile.
```

**两个信号预算**：每镜最多 2 个跨层级信号（眼神 + 呼吸、手 + 重心），至少一个是当前景别看得见的身体或声音信号；不写"五官全动"。微表情时长刻度：0.25–0.5s 闪现（鼻翼、咬肌、眼睛一瞥）；0.5–1s 视线变化、嘴角收紧、抬下巴；1–1.5s 完整转变（笑容褪去、强作镇定）；1.5–2s 面具切换（温柔转算计）。5 秒镜 = 台词发声 + 至多一次 1–1.5 秒的完整转变；面具切换单独给一镜。

**情绪保护层就是憋屈 → 反击的骨架**：礼貌压住怨恨 → 语气变尖 → 嘴角收紧 → 直接指控。这条弧通常跨多镜分布：憋屈镜只演"护层 + 一次泄漏"，底牌镜演"裂缝"，反击镜演"真实情绪变成动作"。反派破防走另一条：讥笑护住羞耻 → 笑僵 → 视线落下。

**5 秒人物镜常用八种表演**（写成可见动作，不写比喻）：

| 用在 | 写法 |
|---|---|
| 反派/旁观者看到底牌（震惊） | 眼睁大、眉提、下颌松，定住后迟一拍眨眼；必须有明确触发词 |
| 反派从不信到认出（怀疑→顿悟） | 侧向锁住线索，证据出现后目光重锁、无声吸气；不直接跳到大幅震惊 |
| 憋屈段反派的轻蔑（得意） | 一侧嘴角挑起、下巴微扬、不回避的注视 |
| 主角由忍转攻（决心） | 视线从低处抬起固定、深吸一口气、咬肌收紧，一个小动作确认 |
| 主角强撑体面 / 反派硬撑面子（紧张假笑） | 嘴笑眼不笑，加一次吞咽 |
| 主角被羞辱时压住的怒（克制的盛怒） | 少露齿、少前冲；只在拳头、下颌、呼吸上 |
| 兑现段反派被打脸（尴尬） | 视线落向侧下、半笑、低头转开 |
| 冷静反杀（复仇决心） | 表情变平静而不是狂躁；语速放慢，动作变少 |

## 6. 运镜：5 秒人物镜常用八种

运镜词属于方言。H3 官方运镜词表 [官方]：`Push In / Pull Out`、`Zoom In / Zoom Out`、`Pan Left / Right`、`Truck Left / Right`、`Tilt Up / Down`、`Pedestal Up / Down`、`Arc Shot`、`Tracking Shot`、`Static Shot`、`Shake Slightly / Strongly`、`POV`、`Roll Clockwise / Counterclockwise`。**官方表里没有 `handheld`**。旧项目头部句里的 `Handheld camera with small natural breathing sway` 已停用：头部句不许带任何运镜词（video-prompts-general §2b 一，G54 L14），它和正文的锁机位同时出现时，模型会把轻晃累积成摇镜。需要手持感的镜只在正文镜头行写 `the camera shakes slightly around a fixed position; the framing stays <景别>, no pan, no tilt, no zoom`，同一镜不写 locked。表外的运镜写成画面关系变化（"主体占画比慢慢变大"）。

`[Push in]`、`[Truck left, Pan right]` 这类方括号运镜指令只属于 MiniMax-Hailuo 2.x 与 I2V-01-Director，不属于 H3 [官方]；H3 正文里的运镜一律写成自然句，不混方括号指令。

远景、全景里的主要人物用背影、后四分之三侧或侧剪影（`seen from behind`、`rear three-quarter view`），正脸留给中近景和特写：远处的小正脸最容易崩脸、换脸 [官方示例；与 EP001 远景脸糊一致，自测]。

完整写法 = 类型 + 幅度（`with small amplitude` / `with large amplitude`）+ 速度（`at slow speed` / `at fast speed`），中等幅度和常速省略不写；写成句中的自然动作，不把标签堆在句尾：`The camera pushes in with small amplitude at slow speed toward her hand.` [官方]。每个运镜写清起始构图、何时因何开始、方向节奏、结束构图；删掉它剧情没有损失就改成锁定。

| 运镜 | 用在 |
|---|---|
| Static / locked | 台词镜默认值：口型可读，节奏交给剪辑；憋屈段的压迫感 |
| 小幅慢推 `pushes in with small amplitude at slow speed` | 底牌亮出或认出真相那一拍，推到脸或手中物件，落点停稳 |
| `tilts down at slow speed` | 机位不动，从脸摇到手里的底牌（卡、证件、合同） |
| `tilts up` | 从鞋或手摇到脸：登场、站起反击 |
| 一次快推 `pushes in at fast speed` | 反派看到底牌的一瞬；一场戏只用一次 |
| 小幅弧线 `makes an arc shot with small amplitude` | 反击时从正面转到侧面，背景变化表现权力翻转 |
| 正文写 `the camera shakes slightly around a fixed position`（不进头部句，不和 locked 同镜） | 憋屈、被围时轻晃；反击成功后切回稳定；非真人画风不用 |
| 反向跟拍 `Tracking shot: the camera moves backward as she walks toward it` | 主角正面走向镜头逼近画外对手 |

景别随心理防线收紧：憋屈段守在中近景/过肩，底牌与反击才进近景、大特写。

## 7. 可生成性改写阶梯

高风险（生成管线里整镜常不可用）：精确拦截（在运动中截住某物）、不可见内部状态、否定式动作、一拍三步以上的双手编排、厘米级位移、单指操作小部件、承重的微表情。

改写：换承担者（物件/环境） → 拆到相邻镜（动作前 / 结果） → 换成停留 → 交给声音 → 标高风险并降级。例：「用手挡住正在合上的笔记本」→「合上笔记本，手放在盖子上没有移开」。

同一镜两次单变量修改仍不过时，按 [video-prompts-general.md](video-prompts-general.md) §11 剥离重建：H3 里先把运镜改成 `The camera holds a static shot.`，再把动作减到一个，再暂时去掉背景人和环境动态，拿到可用 take 后逐层加回。

常见动作放心写：坐下、站起、递东西、点头、回头、抱紧、放下杯子、把纸推过去、拔走 U 盘、举高手机、手一扫碰倒酒杯（酒洒在桌布上，一条只写这一个动作）。出拳用过肩镜、命中帧起震屏，挨打后接踉跄撞物。

## 8. 听者镜与反应优先

事件靠画外声、视线、物体响应证明，镜头留给反应的人；不为了证明每个名词切到手机、把手、脚印。听者对哪个词反应要写清：`On 「授権」 her eyes lift from the paper to screen left; she does not speak, lips closed.` 不许冻住等轮次，也不为每个听者发明小动作。

## 9. 实战骨架与示例

实战项目通过审查的写法（`drama.json` 的 `video_prompt_head` 就是它）：

```text
integrated_multimodal_description: [Shot 1] Single continuous take, no cuts, no transitions, no scene change, starting exactly from the opening frame. Real-time speed, realistic human behaviour with blinking, breathing and small weight shifts; the action continues for the whole take with no frozen pause. No subtitles, captions or on-screen text at any time. Her hand leaves the pen. At about half a second the woman (S1), on-screen, with a young woman's calm, clear voice, says in Japanese, evenly: <d>[Japanese] 名前は消していいです。承認は、あなたがどうぞ。</d> On 「あなたが」 her chin lifts slightly; after the line she keeps looking toward screen left, not smiling. These are the only words spoken in this shot, each said exactly once; nobody speaks before the first line or after the last.
overall_soundscape: quiet meeting room, the faint fan of a projector, a distant office phone. These are the only sounds in the shot.
non_diegetic_music: N/A
```

**这句头部只适用于真人画风（`live_*`）和 `cg_realistic`。** 头部句不写运镜（原来的 `Handheld camera with small natural breathing sway` 已移出，需要不稳感的镜在正文镜头一行写，video-prompts-general §2b 一）。其他画风（`anime_cel`、`manhwa`、`guoman_3d`）不写 `realistic human behaviour`（会把画面往真人实拍拉），`video_prompt_head` 一律用 [styles.md](styles.md) §1 表里对应画风的"视频头句 + 视频保持句"拼接而成，本文件不另写一份，避免两处定稿不一致。风格句本身（起始帧用的 `Style: …`）也以 styles.md 为准。`shots_tool.py` 的默认头部是否按风格切换不归本文件管，写 `drama.json` 时按 styles.md §1 手动选。

写进 `shots.json` 时可以只写 `video_body`（从 "Her hand leaves…" 起）和 `soundscape`，`shots_tool.py build` 拼上头部和 N/A。人名：H3 正文建议用 `the woman (S1)` 而不是名字（G17 warn）；起始帧提示词里可以用名字。

**全身动作实测成功例（滑倒，E36）**：起始帧是贴地机位、只拍到小腿和鞋，鞋尖朝洗手台。前 4 条失败的提示词经过攻防修补成下面这版，拍出了打滑倒地（fal H3 Max Turbo 480P，5 秒）；但倒下太慢、像坐下，因为没写速度、失控和撞击，照抄时按 video-prompts-general §2b 三「物理按常识写」补上。管用的地方：朝向先写死、方向用实物加画面侧、位移按地砖数、每个时间窗一个动作、倒下的画内证据（裙摆和膝盖掉到地面）、终点留在画内、锁机位写全。

```text
integrated_multimodal_description: [Shot 1] Single continuous locked-off take from the opening frame, real-time speed; the camera stays fixed on the floor with no pan, no tilt, no shake, no reframing, no cuts, no zoom and no on-screen text. The only person is Mio; no hands enter the frame. At the start her lower legs hang down into the frame from its top edge, her toes pointing toward the vanity side of the frame (the screen-left side) and her heels toward the door side (the screen-right side); both shoes stay on her feet for the whole clip. At 1.0 seconds the rear shoe, the one nearer the door, swings forward past the other shoe and lands flat on the wet tile one full stride further toward the vanity side. From 1.2 to 1.8 seconds that front shoe slides fast along the floor across three tiles toward the vanity side, from the middle of the frame to the screen-left third, while her ankles buckle and the rear shoe lifts off the tile. From 1.8 to 2.5 seconds she falls backward toward the door side: her dress hem and knees drop down from the top edge of the frame to the floor, and both legs land flat on the wet tile, lying along the floor with her toes pointing up; her hips and upper body are outside the screen-right edge of the frame, beside the door. Her dress stays above her knees and never covers her lower legs. From 2.5 seconds to the end of the clip her legs lie still on the tile in exactly this position, fully inside the frame, clearly visible and in focus. No one speaks.
overall_soundscape: low hum of a restroom ventilation fan; one heel click at 1.0 seconds; a short wet rubber squeak from 1.2 to 1.8 seconds; Mio's own short wordless startled gasp, a young woman's voice, at 1.5 seconds; the heavy thud and wet slap of her body hitting the tile just outside the screen-right edge of the frame at 2.4 seconds. These are the only sounds in the shot.
non_diegetic_music: N/A
```

## 10. 自检清单

1. 三段齐全，`non_diegetic_music: N/A` 在场，`<d>[语种] …</d>` 逐字等于剧本（G09/G10）。
2. 说话对象入画（或写了过搬家测试的 `single_reason`）；video-prompts-general §2b 封闭清单齐全；不开口的可见脸写 lips closed。
3. 开口时机符合项目口味（commercial_fast 才要求 ≤1 秒）；动作镜里解释性台词在动作之后、受击反应与动作同时（video-prompts-general §4 第 3 条）；容量按发声窗口算（G04/G05）。
4. 起点 = 起始帧姿态；唯一动作；终点 = end_state；摄影机写了锁定或移动。
5. 触发词 + 一个变化 + 余态；最多两个信号。
6. 没有否定式动作、没有分支词、没有文件名/ID；左右指画面左右。
7. 无台词镜写 says nothing；声景不含对白；底声与同场相邻镜一致。
7b. 核对通则：主动作可读、起止合理、无冲突约束；需要环境运动才填写；说话者和表演与剧情一致。
8. 说话人音色描述与 refs.json 的 `voice` 一致（G21）。
9. 台词语种标签等于 `dialogue_lang`；说话人视线方向和对象写了，与 `gaze` 一致（G43、G44）。
10. 同一个人的长镜头：多句台词各挂一拍、中间有过渡、最多一次运镜变化（video-prompts-general §3b）。

## 11. 参考模式：首尾帧、六段 full-reference、素材上限与续接

本流程默认一镜一次生成、起始帧 `first_frame` 三段结构（§1）。以下写法只在用户或决策记录选定对应模式、且中转/接口已验证支持时使用；模式由本镜实际挂的图决定，不由"想不想多模态"决定：

| 本镜送出的素材 | H3 模式 | 正文结构 |
|---|---|---|
| 只有起始帧 | `first_frame` | 三段 |
| 起始帧 + 尾帧 | `first_last_frame` | 三段 |
| 起始帧与身份图/底板同时送，或只送身份图/底板 | `reference`（full-reference） | 六段 |

H3 官方另有只给尾帧、由模型推断开场的模式，本流程不用：开场由 `boundary.start` 和起始帧决定。

**首尾帧正文顺序**（官方推荐）：起始帧状态 → 看得见的中间变化 → 与尾帧的差异逐步缩小 → 尾帧状态。默认只有 `[Shot 1]`，不复述两张图的外观，只写连起来的运动路径，最后一句明确落到尾帧（Picture 2）的姿态、间距和构图；中途必须看到的动作不交给插值（video-prompts-general §7c）。风格短语按项目锁定画风写（styles.md §1），不固定为真人。

**full-reference 六段**：`subject_definitions` / `summary` / `retention_analysis` / `detailed_description`（`[Shot 1] …`，台词与同步声音在这里）/ `overall_soundscape` / `non_diegetic_music`。六段是**一条**提示词，一次整体提交。

- **编号**：`<Picture N>`、`<Video N>`、`<Audio N>` 按同类素材的送出顺序各自从 1 递增，必须与请求里 `content` 的顺序一致（providers.py 按同一顺序附加参考约束）；两套编号不一致时模型收到互相矛盾的说明，而接口不报错。写正文前先把本镜素材按顺序列一遍：起始帧 → `<Picture 1>`，身份图 → `<Picture 2>`，底板 → `<Picture 3>`。
- **`subject_definitions`** 把每个主体绑到标签：`<Subject 1> is the high-school girl in <Picture 2>, with …`；说话人物同时写 `<Subject 1> (S1)`。
- **`retention_analysis`** 逐条写保留强度和出现镜次：图片用 `fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference`，音频用 `fully_copy` / `partially_copy` / `reference` / `weak_reference`，例 `<Subject 1> (appears in [Shot 1]): fully_preserved - face shape, hairline and uniform colours stay identical; pose and expression follow this shot, not <Picture 2>.`
- **每张图只负责一件事**：起始帧只锚开场构图与姿态，身份图只锚长相体态，底板只锚空间关系；写进 `retention_analysis`，不让身份图顺带决定构图、底板顺带决定长相。生成后分别检查身份、构图和地理是否保留。
- 不为"多模态"把所有资产图都挂上，只挂本镜真正可见且需要保持的图。

**素材上限**（官方接口）：一次最多 1 张首帧、1 张尾帧、9 张 `reference_image`、3 段 `reference_video`、3 段 `reference_audio`；视频与音频每段 2–15 秒、各自合计 ≤ 15 秒。分辨率 `768P` 或 `2K`；`MiniMax-H3-Max` 是另一型号：5–15 秒、`480P`/`768P`，只支持文生和首尾帧，不支持 full-reference，不能把 H3 的 4 秒下限和参考音频套到它上面。超上限时在分镜阶段按重要性取舍，并写明放弃了哪张。

**首尾帧与参考输入互斥**：同一请求里不能混用 `first_frame`/`last_frame` 和 `reference_*`。"起始帧 + 身份图 + 底板"不拆成首帧加参考图，整组走 full-reference，起始帧也以 `reference_image` 送入。

**续接上一段实际结果**（用户选定续接时，规则同 video-prompts-seedance §5）：上一段实际视频走 `reference_video`（`<Video 1>`，承接动作、节奏、声音），从它抽出的实际尾帧走 `reference_image`（`<Picture 1>`，只作新段开场的姿态与构图锚点），统一 full-reference；不要把尾帧标成 `first_frame`。

**参考音频**：只参照音色、情绪或说话方式时用 `reference`，它会重新表演本镜台词，不能拿参考音频的长度当新台词时长；整条已接受的声音轨原样复用用 `fully_copy`，只用对白层或片段另加环境声用 `partially_copy`，写清源片段与目标时间的对应。参考音频必须和至少一张参考图或一段参考视频一起走 full-reference。这些是复用意图，不是验收证明：生成后核听逐字、语速、停顿、尾音和口型，需要精确锁定已有音轨时以后期保留该音轨为准。

**`<scenetrans>` 与 `<cutoff>`**：`<scenetrans>` 只用于一次生成内的跨切镜发声，本流程一次生成只拍一个镜头、头部句写 `no cuts`，不用它，也不用 `[Shot 2] At 00:03.500, the camera cuts to …` 这类镜内切换语法（跨镜台词在剪辑层做 L/J-cut）。`<cutoff>` 表示视频结束时有意截断发声，只用于剧本本来就要求被打断的那句，不用来处理装不下的完整台词。

**Context-IR**：H3-Context-IR 把多模态输入增强成结构化提示词，本身不生成视频，也不替代对白预算；用了它就核对增强后的逐字台词、声音时间线和时长仍与原稿一致。

## 来源（2026-09-25 补充）

- §6 运镜词表与"类型 + 幅度 + 速度"写法：[H3 Base 视频提示词写作指南](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md) §4.3（已核对官方表里没有 handheld）。
- §7 剥离重建：[Sora 2 提示词指南](https://github.com/openai/openai-cookbook/blob/main/examples/sora/sora2_prompting_guide.ipynb) 的迭代一节。
- §9 分风格头部句：fal 托管的 H3 官方示例、atlascloud 的 H3 拆解、Seedance 2.5 动漫教程的漂移诱因清单（汇总见 `~/Desktop/ai-drama-skill-refs/_reports/2026-09-25-styles.md`）。
- §11 参考模式：[Full-reference 指南](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt)、[Base 指南](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt)、[视频生成 API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)（输入互斥、素材上限、型号差异）、[Context-IR API](https://platform.minimax.io/docs/api-reference/video-generation-v2-h3-context-ir)，2026-09-07 核对；Hailuo 方括号运镜：[Hailuo 图生视频 API](https://platform.minimax.io/docs/api-reference/video-generation-i2v)。

## 台词表演（情绪要写到模型听得出来）

形容词+音量（`furious, fast and loud`）只会被演成「大声」。每句台词在 `<d>` 前写四层，缺一层情绪就会变平；第 4 层"脸与身体"受 §5「两个信号预算」约束，只挑当前景别读得到的两个信号、按 video-prompts-general §2b「朝向与视线」一行的三档写强度，脸的档和声音的档各自对 `emotion`，其余交给声音层：

1. **内心**：只写成声音的色彩，`in a voice of humiliated indignation`；不写事件从句（`the place he earned is being stolen in front of him`、`because …`）——模型会把事件照字面画出来，比如让一个人进画来「偷位置」（G54 L23）
2. **声音质感**：`through gritted teeth, his voice cracking at the top` / `trembling with suppressed rage` / `a choked, disbelieving whisper` / `cold and slow, each word bitten off`
3. **重音与节奏**：`stressing "我"`, `rising sharply at the end`, `said in one smooth unbroken breath, each syllable exactly once`；气息写在开口前的动作里（`he sucks in a sharp breath, then says`）；句中、句后不写 pause / beat / silence（E31：模型会在停顿处补字）
4. **脸与身体**（挑两个）：`brows knotted`、`eyes reddening`、`jaw clenched`、`nostrils flaring`

同是大声，愤怒（咬牙、破音、重音砸在关键字）、惊恐（气短、音高失控、尾音劈）、得意（慢、上扬、带笑气）、威胁（压低、慢而连贯、重音砸在关键字上）写法完全不同。`shouts` 只在真要喊时写，而且必须同时写内心与声音质感。情绪标签（`emotion`：情绪·强度·语速·音量）是给人看的摘要，不能原样翻译成提示词。
