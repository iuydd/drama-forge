# 视频提示词：MiniMax H3 方言 + 表演与对白层

阶段 E 写 `shots.json` 的 `video_prompt`（或 `video_body` + `soundscape`，由 `shots_tool.py build` 拼骨架）时读本文件。来源：本地 `short-drama-video-prompts`（minimax-h3、production-prompt-grammar、motion-recipe、performance-action-timing、generability、camera-audio-continuity）、cinematic-video-prompt-engineer 的表演/对白/运镜库、shuohao 的 H3 结构对账，以及实战项目通过审查的写法。

## 目录

1. H3 三段骨架与硬规则
2. 一镜一人与口型
3. 台词多、反应快
4. 正文怎么写：起点 → 唯一动作 → 台词挂拍 → 终点
5. 表演层：触发词、两个信号、情绪保护层
6. 运镜：5 秒单人镜常用八种
7. 可生成性改写阶梯
8. 听者镜与反应优先
9. 实战骨架与示例
10. 自检清单

## 1. H3 三段骨架与硬规则

```text
integrated_multimodal_description: [Shot 1] <头部固定句> <起点> <唯一动作> <台词事件> <终点>
overall_soundscape: <环境声 / 音效 / 非语言人声；不重复对白>
non_diegetic_music: N/A
```

- `duration` 是 4–15 的**整数秒**，由 `shots.json` 的 `seconds` 决定；正文里的秒数不能代替请求时长。
- 起始帧图生视频走 `first_frame`（`image_mode: keyframe`），三段结构；起始帧只锚定开场构图与姿态，不锁整镜画面语法。起始帧和参考图/参考音频**互斥**，要挂身份图就整组走六段 full-reference（自建 API 是否支持要先验证；现阶段默认三段）。
- 结构字段用英文；台词写 `<d>[Japanese] 逐字台词</d>`，`<d>` 里只放语言标签和台词原文，秒数、声线、语速写在外面；每句只出现一次，紧跟在说话人的可见动作句后；不加剧本外的前导句。
- 说话人稳定 ID `(S1)`：第一次出现时在 `<d>` 外交代画内/画外和音色；同一角色全剧用同一段音色描述（写在 refs.json 的 `voice`，G21 对账），这是首帧模式下减少逐镜音色漂移的唯一办法。
- `non_diegetic_music: N/A` 必须显式写；省略这一层小样本里出现过额外配乐。配乐在剪辑层加。
- 无对白镜写 `He says nothing. No other voices speak words.`，否则模型会自编人声（审片时 ASR 会抓）。
- 正文 ≤ 7000 字符；5 秒单人镜约 150–250 词写满，超 300 词多半冗余。
- **正面描述、不留分支**：`不要进红框` → `直接进蓝框`；不出现 `or / 或 / 二选一 / 可选`（G22）。否定式动作改写成可见动作。
- **交付文本只含要拍的内容**：不写文件名、ID、规则号、重投备注、无关否定罗列。"锁定参考图" → "衣着与起点一致"。
- 裸写的 left/right 一律指**画面**左右；人物自身的左右带主体（"his left hand"）。
- 摄影机一栏不能空着：锁定也要写（景别 + 机位高度 + 保持多久），空着会被读成可以自由漂移。
- 声景是动作指令：声景里写了撞击，画面就会演出撞击。同场相邻镜底声写成一致，否则切点会"呼"一声换空间。

## 2. 一镜一人与口型

本地实测：近处骑手正脸不说话时，旧写法 3 次里 2 次把口型放到骑手脸上；补"骑手不说话、嘴唇紧闭"后 3/3 正确；骑手出画或背身 12/12 正确。**模型把口型放到画面里最显眼的正脸上。**所以：

- 一个镜头只拍一个人或一双手；对手戏拆成单人正反打。
- 画内确有第二张脸（只允许在 `multi_person_reason` 成立时）：`<Other> does not speak; his lips remain completely closed.`
- 画外台词（`[OS]`）叠在听者的反应镜上时，写清画外说话人的声线，并明写听者嘴唇闭合。

## 3. 台词多、反应快

项目口味，已经写进门：

- 人物镜默认有一句台词；第一句在 1 秒内开口（G05）。反应类台词写 `At the same instant` / `at about a quarter of a second`；被抢、被打、被戳穿当场出声。
- 对白预算：`发声窗口 = 镜长 − 开口前等待 − 不能并行的动作 − 其他人发声 − 末尾落点(0.5–1.0s)`。5 秒镜约 3.8 秒发声，中文约 15 字（H3 实测 4.1 字/秒），日语按 `speech_rates.ja` 估、用首批 ASR 实测校准（G04 用它算容量）。
- 放不下时的降负载顺序（不许加速、截断、静默删字）：删装饰性运镜 → 删次要手势和环境小动作 → 让台词跨到反应镜（剪辑层 L/J-cut） → 加 1–2 秒（≤8） → 拆镜。台词只能回剧本阶段改。
- 抢话只在同一次生成内成立：写清入场触发词、谁让位、被打断者嘴停在哪；跨镜抢话放到剪辑层。

## 4. 正文怎么写

节拍链：`从<最少起点>开始。首先<起手>；接着<动作、方向、幅度>；随后<结果>；与此同时<另一通道：呼吸/视线/手>；最终<终点>。摄影机<锁定或移动及其目的>。台词挂在它发生的那一拍。`

七项检查：起手｜串行链带方向幅度｜至少一处量级（约半步、约一掌、约三十度）｜一条并行通道｜结束状态｜摄影机及其目的｜台词挂拍。

- 起点 = 起始帧的可见姿态，不复述静态外观（衣服、脸、背景由起始帧承担）。
- 一镜一个主导变化、一个主运镜；上一镜已完成的推近或动作不在下一镜重来；每镜结束形成新状态，终点 = `end_state`，下一镜从它接。
- 显式分段时，各段并集必须正好等于镜长；余量会被模型用无来源动作填满。
- 生成优先级梯（指令冲突时先简化低优先级项）：台词顺序、说话者身份、口型 > 听者反应 > 连续手势与视线 > 镜头装饰与环境细节。

## 5. 表演层

**压缩版表情时间轴**（5 秒镜只留三样）：触发词 + 一个面部或身体变化 + 说后余态。

```text
At about half a second the man (S2), on-screen, with a smooth condescending voice, says in Japanese: <d>[Japanese] 君がいなくても、回るよ。</d>
On 「回るよ」 one hand opens outward in a small shrug; after the line the grin stays.
```

**两个信号预算**：每镜最多 2 个跨层级信号（眼神 + 呼吸、手 + 重心），至少一个是当前景别看得见的身体或声音信号；不写"五官全动"。微表情时长刻度：0.25–0.5s 闪现（鼻翼、咬肌、眼睛一瞥）；0.5–1s 视线变化、嘴角收紧、抬下巴；1–1.5s 完整转变（笑容褪去、强作镇定）；1.5–2s 面具切换（温柔转算计）。5 秒镜 = 台词发声 + 至多一次 1–1.5 秒的完整转变；面具切换单独给一镜。

**情绪保护层就是憋屈 → 反击的骨架**：礼貌压住怨恨 → 停顿变尖 → 嘴角收紧 → 直接指控。一镜一人时这条弧跨多镜分布：憋屈镜只演"护层 + 一次泄漏"，底牌镜演"裂缝"，反击镜演"真实情绪变成动作"。反派破防走另一条：讥笑护住羞耻 → 笑僵 → 视线落下。

**5 秒单人镜常用八种表演**（写成可见动作，不写比喻）：

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

## 6. 运镜：5 秒单人镜常用八种

运镜词属于方言：用 H3 官方指南记载或本项目实测过的词（`push in`、`pull out`、`pan left/right`、`tilt up/down`、`tracking shot`、`static shot`、`handheld`），查不到的写成画面关系变化（"主体占画比慢慢变大"）。每个运镜写清起始构图、何时因何开始、方向节奏、结束构图；删掉它剧情没有损失就改成锁定。

| 运镜 | 用在 |
|---|---|
| Static / locked | 台词镜默认值：口型可读，节奏交给剪辑；憋屈段的压迫感 |
| 极慢 push in | 底牌亮出或认出真相那一拍，推到脸或手中物件，落点停稳 |
| tilt down | 机位不动，从脸摇到手里的底牌（卡、证件、合同） |
| tilt up | 从鞋或手摇到脸：登场、站起反击 |
| 一次快速 push in | 反派看到底牌的一瞬；一场戏只用一次 |
| 浅弧 arc | 反击时从正面转到侧面，背景变化表现权力翻转 |
| 克制 handheld | 憋屈、被围时轻晃；反击成功后切回稳定 |
| 反向跟拍 | 主角正面走向镜头逼近画外对手 |

景别随心理防线收紧：憋屈段守在中近景/过肩，底牌与反击才进近景、大特写。

## 7. 可生成性改写阶梯

高风险（生成管线里整镜常不可用）：精确拦截（在运动中截住某物）、不可见内部状态、否定式动作、一拍三步以上的双手编排、厘米级位移、单指操作小部件、承重的微表情。

改写：换承担者（物件/环境） → 拆到相邻镜（动作前 / 结果） → 换成停留 → 交给声音 → 标高风险并降级。例：「用手挡住正在合上的笔记本」→「合上笔记本，手放在盖子上没有移开」。

常见动作放心写：坐下、站起、递东西、点头、回头、抱紧、放下杯子、把纸推过去、拔走 U 盘、举高手机。出拳用过肩镜、命中帧起震屏，挨打后接踉跄撞物。

## 8. 听者镜与反应优先

事件靠画外声、视线、物体响应证明，镜头留给反应的人；不为了证明每个名词切到手机、把手、脚印。听者对哪个词反应要写清：`On 「授権」 her eyes lift from the paper to screen left; she does not speak, lips closed.` 不许冻住等轮次，也不为每个听者发明小动作。

## 9. 实战骨架与示例

实战项目通过审查的写法（`drama.json` 的 `video_prompt_head` 就是它）：

```text
integrated_multimodal_description: [Shot 1] Single continuous take, no cuts, no scene change, starting exactly from the opening frame. Handheld camera with small natural breathing sway, real-time speed, realistic human behaviour with blinking, breathing and small weight shifts; the action continues for the whole take with no frozen pause. No subtitles, captions or on-screen text at any time. Her hand leaves the pen. At about half a second the woman (S1), on-screen, with a young woman's calm, clear voice, says in Japanese, evenly: <d>[Japanese] 名前は消していいです。承認は、あなたがどうぞ。</d> On 「あなたが」 her chin lifts slightly; after the line she keeps looking toward screen left, not smiling.
overall_soundscape: quiet meeting room, the faint fan of a projector, a distant office phone.
non_diegetic_music: N/A
```

写进 `shots.json` 时可以只写 `video_body`（从 "Her hand leaves…" 起）和 `soundscape`，`shots_tool.py build` 拼上头部和 N/A。人名：H3 正文建议用 `the woman (S1)` 而不是名字（G17 warn）；起始帧提示词里可以用名字。

## 10. 自检清单

1. 三段齐全，`non_diegetic_music: N/A` 在场，`<d>[语种] …</d>` 逐字等于剧本（G09/G10）。
2. 一镜一人；画内其他脸写 lips closed。
3. 第一句 ≤1 秒开口；容量按发声窗口算（G04/G05）。
4. 起点 = 起始帧姿态；唯一动作；终点 = end_state；摄影机写了锁定或移动。
5. 触发词 + 一个变化 + 余态；最多两个信号。
6. 没有否定式动作、没有分支词、没有文件名/ID；左右指画面左右。
7. 无台词镜写 says nothing；声景不含对白；底声与同场相邻镜一致。
8. 说话人音色描述与 refs.json 的 `voice` 一致（G21）。
