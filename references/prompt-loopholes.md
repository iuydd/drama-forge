# 提示词漏洞库：生成模型钻过的空子

记录生成模型（图生视频、图片编辑、TTS）在**不违反提示词字面**的前提下交出坏成品的方式。来源只有两种：实拍失败复盘、攻防子代理（SKILL.md 硬约束 11d）清单里的致命条目。

**怎么用**
- 写提示词前扫一遍本表，按「堵法」写。
- 每次攻击清单里的致命条目、每次生成失败复盘出的新漏洞，照格式追加一行，编号只增不改。
- 同一漏洞出现 ≥ 2 次、而且能写成规则的，升级进机械门 G54（`shots_tool.py check` 逐镜查 video_prompt，报 warn），在「机械检查」列写上；写不成规则的留给攻击子代理查。
- 已升级的条目误报了就回来改规则，不靠豁免堆着（总则 9）。

| 编号 | 漏洞（模型怎么钻） | 实例 | 堵法 | 机械检查 |
|---|---|---|---|---|
| L01 | 写 left/right，人物对着镜头时左右读反，模型和写的人都会搞反 | 2026-09-26 洗手间滑倒：鞋尖朝洗手台（画面左），提示词却让她朝画面右的门走 | 用画面里的实物做参照（朝洗手台、往门那边倒）；非写不可写 screen-left 并在同一句写人物朝向 | G54 L01 |
| L02 | 只写「锁定机位」没封住 pan/tilt/zoom/cut，模型用摇镜代替人物动作 | 8 动作测试和滑倒 v1：人该后仰、该倒下的那一刻，画面整体摇走 | 锁定写全 `no pan, no tilt, no shake, no reframing, no zoom, no cuts` | G54 L02 |
| L03 | 位移没有可量的距离，模型挪几厘米交差，480P 下只剩一团糊影 | 滑倒 v2「slides about half a metre」被攻击者指出可只做 10 cm | 按画面里可数的东西写：`across three tiles`、`one full stride` | G54 L03 |
| L04 | 一个时间窗塞几个动作、一条视频塞几个主动作，最难的那个被丢掉 | 8 动作测试：小动作都做了，唯一的全身动作（椅子后滑）没做 | 一条视频一个主动作（video-prompts-general §3），每个时间窗一个动作 | G54 L04 |
| L05 | 物理动作没写速度、失控和落地，模型用慢而可控的动作交差 | 滑倒 v4：倒下用了近 1 秒、像屈膝坐下 | 按常识写多快（不到半秒）、失控（不屈膝放下自己）、怎么砸地（反弹、溅水、闷响） | G54 L05 |
| L06 | 终点句「离开画面」「倒出画面」没写路径，模型选最省事的路径（走出去） | 滑倒 v1 及 H3 3 条：人走两步从侧边走出画面，字面满足「双脚离开画面」 | 写明从哪条画框边、以什么方式离开；难动作前不写普通走动 | G54 L06 |
| L07 | 提示词和起始帧里人物的朝向、姿态矛盾，模型按起始帧来、改掉动作 | 滑倒：起始帧站定且鞋尖朝洗手台，提示词写朝门迈步 | 先看起始帧，把人朝哪、站还是走写死一句，动作方向跟着它 | 攻击子代理 |
| L08 | 物理上做不到的轨迹，模型换成它做得到的动作 | 贴地机位写「脚往上飞出画面」「倒出画面只剩空地板」，模型改成走出去或凭空消失 | 写之前按常识推一遍：人往后摔脚往前踢、身体会砸进画面 | 攻击子代理 |
| L09 | 难动作前写了普通动作（朝门走），模型只做普通的那个 | 滑倒 v1 | 难动作直接从起点写起，前面不放可替代它的普通动作 | 攻击子代理 |
| L10 | 只封「台词」没封非语言人声和音效，模型加笑声、惨叫、雷声 | 恶意模型攻击 65 个成品（2026-09-26） | 声景末尾写 `These are the only sounds in the shot.` | 攻击子代理 |
| L11 | 只给剧情道具写数量，陈设不写，模型按「这种场景应该有」多补一件 | 2026-09-27 书房：多出一只箱子 | 画内每类可数陈设写 `exactly N`，末尾同类排他句 `There are no other boxes, crates or containers anywhere in the room.`（video-prompts-general §2b 陈设清点） | G54 L11 |
| L12 | 位置只写 `beside` / `next to` 或画左画右，没写以镜头为准的前后，模型把物件挪到桌子靠镜头一侧 | 2026-09-27 书房：箱子从桌后跑到桌前 | 三方向写位置：`on the floor between the desk and the back wall, on the far side of the desk from the camera` | G54 L12 |
| L13 | 门窗只写 open，开度是二值，模型每镜给一个开度，镜内还会自己动 | 2026-09-27 书房门：开度和上一镜不一致 | 写可量开度加参照（`open about one hand's width, roughly 15 degrees`），加 `does not move throughout the entire clip`，与上一镜 `end_state` 逐字一致 | G54 L13 |
| L14 | 头部句带 handheld/sway，正文又写锁机位，模型每秒晃一点累积成摇镜 | 2026-09-27 对抗审查：实例 278 条同时含 handheld 与 no pan | 头部句不带任何运镜词；手持感只在正文写 `shakes slightly around a fixed position`，同镜不写 locked（general §2b 一） | G54 L14（头部句 error） |
| L15 | 必备封口句缺失：没有声音封闭句就加雷声笑声，无对白没写 No one speaks 就自编人声，没写 until the end 结尾乱动 | 对抗审查：实例约 600 条缺 `These are the only sounds` | 四句必备句（general §2b 二b），缺一句 error | G54 L15（error） |
| L16 | `Keep … exactly` / `the scene stays exactly` 集合式保持，模型整体定格或为保底板把人缩小 | §6b 反例；frame_prompt 949 处 Keep | 不变量逐个点名写 `stay where they are`；分工句用 Take … from | G54 L16 |
| L17 | L02 能被 gunshot、medium shot、`no one lifts the pan` 字面满足 | 对抗审查 V04 | 摄影机封口写成独立一句，`no pan, no tilt …` 逗号串接 | G54 L17（修 L02） |
| L18 | L03/L05 的距离、速度、落地词在全文任意处出现就算数，表情句里的 hard 满足速度 | 对抗审查 V05 | 证据写在动作动词那句或下一句 | G54 L18（修 L03/L05） |
| L19 | `walks out of frame toward the door` 满足 L06 路径要求，正是省事路径 | 对抗审查 V06 | 出画写哪条画框边 + 最后离开的身体部位 + 方式 | G54 L19（修 L06） |
| L20 | `to her left` / `on his right` 因带 his/her 被 L01 豁免，恰是必读反的写法 | 对抗审查 V07 | his/her left 只接身体部位 | G54 L20（修 L01） |
| L21 | 起始帧不受 G54 检查，错图被视频忠实接住；静帧里写运动词 | 对抗审查 V08、V09 | 静帧清单（general §2b 二b），不写运动词 | G54 L21 |
| L22 | 有首帧就把外貌锚点全删，模型从第 2 秒开始漂发型、换外套 | 对抗审查 V10 | refs.json `drift_anchors`，每次提到此人带同一短语 | G54 L22 |
| L23 | 台词前写内心事件从句，模型把事件画出来 | 对抗审查 V12（H3 台词四层旧例） | 内心只写成声音色彩 | G54 L23 |
| L24 | 分工句只写取什么，服装、背景、姿势跟着参考图串进来 | 对抗审查 V21 | 分工句两半：sets only … ; … come from this description, not from Picture N | G54 L24 |
| L25 | 光只写方向，模型加第二光源、阴影方向错、同场冷暖跳 | 对抗审查 V20 | 光句写光源个数、实物来源、软硬、阴影落向并排他，同场逐字复制 | G54 L25 |
| L26 | 道具件数对了但换色、换材质、跨镜缩放 | 对抗审查 V23 | 颜色 + 材质 + 尺寸比的固定短语，全集逐字复用 | G54 L26 |
| L27 | 编辑保留清单写 everything else / the rest，失焦后顺带改光改脸 | 对抗审查 V24 | 保留项逐个点名 | G54 L27 |
| L28 | a little / briefly / gently 等伪量词按零或最大值执行 | 对抗审查 V25 | 换成秒数、件数、三档强度词 | G54 L28 |
| L29 | G52 的 blocked_by 全写「验收：」，提示词一字不改；worst 改一个字就不算重复 | 对抗审查 V14 | 「验收：」最多 1 条且带可量检查；相似度 >0.8 算重复 | G54 L29（error） |
| L30 | 审片只看三帧、只数人头、ASR 听不到的声音当没有，多余的人和物只在 0.5–1.5 秒出现 | 对抗审查 V13、V15、V16 | 4fps count_trace + verify_frames、scene_state 逐项计数、VAD 段 vocal_ok（general §2b 七） | G54 L30 |
| L31 | 歧义动词按另一个意思执行：tearing（流泪/撕扯）、shoot（开枪/拍摄）、draw（拔刀/画画）、wave（挥手/浪）、charge（冲锋/充电）、strike（击打/划火柴） | GitHub 提示词 skill 调研（OSideMedia/higgsfield-ai-prompt-skill） | 发出前逐个动词问"它还能被画成另一种画面吗"；能就换成带宾语和身体部位的写法：`tears run down her cheeks`、`pulls the knife from the sheath at his hip` | 攻击子代理查 |
| L32 | 物件按剧情重要性缩放：关键道具画大（手机像平板、刀像剑）、小物画小、跨镜忽大忽小；只写 small/large 时模型自选尺寸 | 用户 2026-09-27 要求物品和人物按真实比例生成 | 厘米尺寸 + 一个身体部位对照，全集逐字复用（storyboard-keyframes §6b 物件真实比例）；目检和最近的身体部位对量 | 攻击子代理查 |
