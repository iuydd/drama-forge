# 参考图提示词：身份图、转面板、底板、道具、状态变体、局部编辑

阶段 D 写 `参考图/refs.json` 的 `prompt` 字段、阶段 F 出参考图和重出时读本文件。"写什么事实"以 [visual-assets.md](visual-assets.md) 为准（身份、变体、平面图、尺度、锁）；本文件只管"这些事实怎样写成一段能直接提交的英文提示词"，以及不同用途、不同模型之间的差别。起始帧提示词的写法在 [storyboard-keyframes.md](storyboard-keyframes.md) §6。

硬规则照旧：提示词正文是英文（G18）；含 `no text`；身份图一个人、写厘米身高；底板 `No people`、写画左画右和尺度参照；道具图 `no hands`（G18–G20、G34）；生成画面里不出任何可读文字（SKILL.md 硬约束 4）；模型、档位、分辨率只用 `drama.json` 里用户定下的 `profiles`（硬约束 1b）。

## 目录

1. 先定这张图只回答哪一个问题
2. 从视觉设定到提示词：四个篮子
3. 各类参考图怎么写
   3.1 全身身份图 · 3.2 头肩图 · 3.3 转面板与裁格 · 3.4 造型/状态变体 · 3.5 底板 · 3.6 道具图 · 3.7 风格帧 · 3.8 尾帧状态图
4. 局部编辑与重出
5. 参考板的布光：按"要比较什么"选
6. 文字在参考图里怎么处理
7. 画风只改"怎么画"，不改"画的是谁"
8. 模型差异
9. 自检、反例与改写

## 1. 先定这张图只回答哪一个问题

每条 refs.json 条目写之前先写一句"复用任务"：下游镜头要靠这张图保持什么——身份、当前造型、某个状态、空间地理，还是道具形制。这句话写进 `controls`，它的反面写进 `not_controls`。一张图只承担一个用途（visual-assets §8 的九类），承担两件事就拆两张。

- 身份图不决定姿势、构图、临时造型；
- 构图、尺度参考只借占比、机位在哪一侧、留白，不带入图里的人和事件；
- 效果参考（烟、光、碎片）只控制目标效果的形态和范围，不让别的东西跟着消失或复制；
- 风格参考只控制表面处理（色层、材质、阴影边缘、景深倾向、画面密度），永远不控制身份、地理、剧情状态、人数、持物。

参考图进项目前必须用当前环境的看图工具看过（尤其用户给的、网上来的、上一轮生成的），看它实际画了什么，而不是看文件名。图里有字、有水印、多一个人、背景有真实校名，就裁掉、模糊或重出后再用；在提示词里写 "no watermark" 擦不掉参考图里已有的像素（visual-assets §8）。没看过的图不绑定。

## 2. 从视觉设定到提示词：四个篮子

不要把整条视觉设定照抄进提示词。先把事实分进四个篮子，再按 visual-assets §7 的八段顺序写：

| 篮子 | 回答的问题 | 写法 |
|---|---|---|
| 识别锚点 | 去掉衣服和天气之后，凭什么认出它 | 可见的形状、比例、相对位置、材质特征 |
| 状态差异 | 这一张和基础版本差在哪 | 有边界、看得见的变化（位置、范围、程度） |
| 复用几何 | 后面的镜头最怕哪里漂 | 方位、尺度、入口、握持面、结构关系 |
| 呈现条件 | 怎样最容易看清以上事实 | 构图、视角、背景、光线、空场 |

选锚点的经验：
- **少而不重复**：一个轮廓、一个比例关系、一个局部特征、一个材质或色彩关系，比十个近义形容词稳。
- **用相对关系写空间**：`the service counter stands to the right of the main entrance; the only metal door is in the back wall`，比散列的物件清单更能被复用。
- **抽象词要换成证据**：`cold, stern` 不够，要落到表情肌肉、站姿、服装线条或冷色光上；但不许为了"冷"去编造伤疤或身份。
- **不假精确**：视觉设定写"二十多岁"就写 `in her twenties`，不写 `23 years old`。
- **审美词要么落到可观察的选择，要么删掉**：`cinematic, premium, high quality, 8K, masterpiece` 不提供识别信息，还会挤掉锚点；风格统一靠 `drama.json` 的 `style` 句（styles.md），不靠每条提示词堆质量词。

正文里不出现 JSON 键名、IMG ID、文件路径、"请务必"、权重语法、审查结论和重试历史；元信息放在 refs.json 的其他字段里。

## 3. 各类参考图怎么写

### 3.1 全身身份图（`IMG-<NAME>`）

写作顺序：用途与主体 → 身份锚点（脸型、发际线、发型剪影、体形、厘米身高、头身比）→ 当前唯一的一套基础造型（从头到脚，服装锁短语逐字）→ 构图（全身、正面、中性表情）→ 均匀光 → 素背景 → `no text` 与排除。

- **只画一套相容的造型**：制服和便装、受伤和无伤、干发和湿发不能同时出现；互斥的东西拆成不同条目。
- **只画常规干净状态**：伤、血、湿身、战损是镜头状态或变体，不进基础卡；以后会消失的饰品不上身份图（G18 警告）。
- **身份锚点来自这个角色自己**：同一批身份图并排读，逐字重复且和角色无关的句子（`perfect proportions, long slender legs`）是模板残留，删掉或改成该角色的真实锚点（G20 查相似度）。
- **排除项只写这张最可能出的错**：`no second outfit, no extra accessories, no props in hand`；不写一长串 "no bad anatomy, no blur" 套话。
- **服装句内部按"形制 → 面料 → 收边与配饰 → 使用痕迹"排序**。第一项必须是这个时代能读出身份的具体款式名（圆领袍、直裰、双排扣大衣、护士服），不能只写"长袍""外套"这类通用轮廓；越靠后的内容越容易在翻译或截断时丢失。形制按项目的时代基准写（visual-assets §1）。（取自 shuohao-skills）
- **"便装""朝服""正装"这类场合标签不写进身份图提示词**，直接写形制本身（"盘领窄袖、金织盘龙补、翼善冠"）。场合标签不提供画面信息，还会把身份图绑定到某个场合上；身份图画人物的常态造型，临时换上的礼服、夜行衣、丧服按造型变体处理（visual-assets §3b）。（取自 shuohao-skills）
- **长期使用痕迹最多写一处，并且说得出是谁、因为什么造成的**（职业、处境、原著依据），说不出来由就不写。磨白、墨迹、补丁叠加三处，"侯府世子"会画成抄书匠。局部细节不等于整体身份：袖口磨白不代表整件衣服粗旧，素簪不代表侍女；整体形制、面料、剪裁负责表达身份，局部痕迹只表达习惯，两者分开写。自检：遮住人物名字只读服装句，读出来的身份和视觉设定一致吗？不一致就改服装句，不改设定。（取自 shuohao-skills）
- **面部写这个人自己的特征，不写渲染质量**：骨相、脸型、五官比例、发际线走向；眉眼可以写成左右略不对称；有年龄的角色，皱纹沿表情肌走（法令纹、鱼尾纹、抬头纹），不是随机刻线。"可见毛孔、次表面散射"只在写实画风里写。排除项只禁"假"和"错"、不禁画风：从 `identical faces across characters, doll-like oversized eyes, over-smoothed skin, perfectly symmetrical face, lifeless eyes without catchlight, helmet-like hair without loose strands, mannequin pose` 里挑这张最可能出的一两项，不写 `photorealistic / anime / 3d render` 这类画风词。（取自 shuohao-skills）
- **中性站姿写 `arms relaxed at the sides`，不写 `hands clasped in front`**：双手交叠在腰前读作"等候吩咐"，会把人物画成仆从（storyboard-keyframes §8c）。（取自 shuohao-skills）

```text
Photorealistic full-body character reference of one Japanese woman in her late twenties, about 160 cm tall, slim build, adult proportions about seven and a half heads tall. Narrow oval face, a small natural break at the tail of her right eyebrow, shoulder-length black hair in a low ponytail. Base outfit only: a charcoal grey blazer over a white shirt, dark straight trousers, black flat shoes. She stands facing the camera, arms relaxed at her sides, calm neutral expression, eyes clearly visible. Soft even studio light, plain light grey background. One person only, nothing in her hands, no jewellery, no second outfit, no text, no logo.
```

### 3.2 头肩身份图（`IMG-<NAME>-FACE`）

做法、绑定规则见 visual-assets §3。提示词写法补充：第一句是保留句（`Keep the same person from Picture 1: same face, hairline, skin tone and build.`），第二句只改构图（头顶到上胸、脸约占画高一半、正面、闭嘴中性表情），第三句写这个人自己的脸部与发型锚点，领口处带服装锁短语；背景和光与全身图一致。

### 3.3 转面板与裁格（`IMG-<NAME>-SHEET` → `IMG-<NAME>-BACK` / `-SIDE`）

背影镜、侧脸镜多的主要人物可以做一张转面板，用来目检和裁单格：

- 以已确认的全身身份图为参考图生图（`refs: ["IMG-<NAME>"]`），不要用文字重新生成一个人；
- 横幅约 2:1（不要把五个视图挤进竖图），一排：正面、四分之三侧、正侧、背面，外加一格头肩；所有视图同一时刻、同一造型、同一比例、同一光；
- 画面内**不要**视图标签、引线箭头、尺寸标注、图注和分隔文字；
- 在 refs.json 条目里写 `"layout": "multi_view"`，`controls` 写"目检与裁格来源"。

**转面板不直接挂进起始帧的 `frame_refs`**：模型会把多格版式或同一人的几个分身复制进画面（`scripts/visual_lint.py` 的 V01 查）。要侧面、背面参考时，从板上裁出那一格，另登记一条 `IMG-<NAME>-BACK`（`kind: identity`，`refs: ["IMG-<NAME>-SHEET"]`，`crop_from` 写来源板，`prompt` 写"从转面板裁出的背面格"并照样写清这个人的锚点）。裁格分辨率偏低，只用于背影、远景、侧面镜。

```text
Keep the same person from Picture 1: same face, hairline, skin tone, build and outfit. Character turnaround reference on a wide landscape sheet: five views of the same woman side by side at the same scale and height — front, three-quarter left, full left profile, back, and a head-and-shoulders close view — all in the same moment, the same outfit and the same soft even studio light on a plain light grey background. About 160 cm tall, adult proportions about seven and a half heads tall, charcoal grey blazer over a white shirt. No view labels, no arrows, no measurement marks, no captions, no text.
```

### 3.4 造型与状态变体（换装、受伤、湿身、伪装、年龄段）

变体是否成立由 visual-assets §2 决定，这里只管写法。每条变体条目必须答得出：基础版本是哪条（`refs` 指向它）、哪些身份事实不变、变化在哪里（位置、范围、程度）、从哪一场生效到哪一场。

- **图生图派生，不重新生成**：`refs: ["IMG-<NAME>"]`；第一句保留句，然后只写差异（visual-assets §3）。年龄段变体例外，见本节末条。
- **动词纪律**：只用 `change only / replace / remove / add` 指向具体对象，不用 `transform / turn into / make it look like / convert into`——整体改写类动词容易把人整个换掉（V03 查）。
- **差异要有边界**：`the right sleeve is soaked dark from the elbow down, the shoulder stays dry` 比 `wet clothes` 可控；不要把"雨后"扩成全身滴水、新伤或换装。
- **差异写在最显眼处**：保留句之后马上写差异，不要复制整段基础描述再把变化藏在末尾。
- **一张只画一个状态**：完好/损坏、白天/夜晚、两套造型不画进同一张；确需前后对照时单独做对照板，不作身份参考挂进起始帧。
- 瞬时表情、一次抬手、单镜姿势归分镜，不建变体图。
- **年龄段变体是例外，不写 `same face`**：幼年、少年、老年版本套用上面的保留句，会得到一张缩小或加了皱纹的成人脸。只保留跨年龄不变的东西（肤色、痣和疤这类永久特征、眼型的大致特征、没变的发色），另外写这个年龄段的脸型和五官比例（幼童脸圆、眼睛占比大；老人颧骨突出、眼窝深）、身高和体态（"身高只到成人的腰""背微驼"）。可以挂成人身份图做参考，但分工句写明它只管"肤色和永久特征"：`Use Picture 1 only for skin tone and permanent marks; this is the same person at about eight years old, with a child's round face…`。年龄段版本单独出头肩图，和成人头肩图并排目检：要读得出是同一个人，又不能看成同龄人。（取自 dramaclaw）

```text
Keep the same person from Picture 1: same face, hairline, skin tone, build and hairstyle. Change only the outfit: add a worn orange raincoat over the same charcoal grey blazer, hood down, zipped halfway. The raincoat's right shoulder is darkened by rain down to the elbow; everything else stays dry. Same full-body front pose, same soft even studio light, same plain light grey background. One person only, no text.
```

### 3.5 底板（`IMG-PLATE-*`）

地理事实、平面图与动线、派生底板的相机操作句、双向对照板后备做法都在 visual-assets §4、§4b。提示词的层次顺序：

1. 这是什么空间、服务什么活动、整体尺度；
2. 相机站在哪、看向哪（平面图锚点）、机位高度；
3. 入口与路线：门、走廊、楼梯的位置和方向（楼梯往上还是往下写死）；
4. 一到三个强锚点及其两两关系、视线终点；有栅栏、门、玻璃、崖沿时写两侧各是什么；次要装饰概括带过；
5. 对辨认结构有用的墙、地、顶材质和主次色，以及这个地点的保养水平（日常使用 / 持续维护，visual-assets §4）；
6. 当前状态：时段、天气、实际灯具开关（跨镜持续的状态才进底板）；
7. `No people.` 与 `No readable text anywhere.`

- 同一个句子里一扇门不能同时在左墙和右墙；画左画右各是什么写死（G19）。
- 前景/中景/后景是可选的组织方法，不是每块底板都要填满三层；单房、需要留白的画面可以不用。
- 气氛（压抑、危险、温暖）只能翻译成已有依据的空间选择：通道窄、光比、材质反射、空气状态、色温关系；不许为了气氛新加事故、封死出口、挪动门窗，也不许凭提示词惯性加霓虹、雾、逆光。
- 底板只画固定陈设和本状态的布景；剧中角色、临时人群、当前动作都不进底板（G19 `No people`），需要人物尺度参照时用门、护栏、桌面这类现实尺寸物件（visual-assets §12）。

### 3.6 道具图（`IMG-PROP-*`）

顺序：类型与主体 → 尺度与轮廓（真实尺寸或与中性参照的比例）→ 主次材料与表面反射 → 功能结构（活动件、开启方向、握持区、接口）→ 当前状态（开合、内容物可见程度、破损位置）→ 视图与素背景、易读光 → `no hands`、`no text` → 排除（变形、错材、多出一件复制品）。

- **一张只画一个明确状态**：开/关两态要用就建两条道具条目，各自登记。
- **尺度参照用中性物**：带刻度的底座、已知尺寸的功能结构（`about 30 cm wide`），不用剧中人物的手当参照（G19 要求 `no hands`）。
- **功能写到能理解，不演剧情**：铰链、扣件、开口画清楚，但不画"正在被打开"。
- **同类物的区分结构优先保住**：钥匙的齿形、药瓶的封口、箱扣的咬合方式是识别通道，画风再简化也不能省。

### 3.7 风格帧（Lookdev，可选）

立项时 `style_preset` 已定（styles.md），但同一 preset 下材质、光色、边缘处理还有差别时，可以在出身份图之前做一到三张风格帧，比较后把结论写进视觉设定的"项目视觉方向"和 `drama.json` 的 `style` 句。三类测试各选最能暴露风险的一张，不凑数：

- **人物表现**：绑定一个已定角色和造型，看身份锚点、线条/材质、表演能不能读；
- **核心地点**：绑定一块主底板，看地理、材质、色彩层级和光源逻辑；
- **高压场面**：绑定剧本里真实的一场和它的信息权限，看冲突里的注意中心、遮挡和画面密度；不为"更有冲击力"提前泄底、编造动作结果或改文字政策。

每张风格帧先写一句"本帧要暴露的风险"，再写跨三类都要保持的规则、本帧允许变化的部分；风格参考图只写它能控制的表面项。比较由 director 和 art-director 完成，选定写进 `项目开发/决策记录.md`（风格帧消耗图片额度，按硬约束 1 的成本边界执行）。

### 3.8 尾帧状态图（可选）

只有当前 `profiles` 里的视频模型支持尾帧、而且这一镜的职责落在"收尾那一下"（坐定、落点、递交完成）时才做。尾帧提示词是镜头 `boundary.end` 的投影，规则与起始帧对称：只写终点已经成立的事实，删掉起点才有、终点已经不在的东西；可以决定构图和光，不能改人在哪、手里有什么、看着谁。尾帧与 `boundary.end` 不一致时，错的是尾帧。写法和取舍见 storyboard-keyframes §5b。

## 4. 局部编辑与重出

重出参考图（`--retake`）或从已有图改一处时，四项缺一不可：

```text
目标：哪条 IMG、哪个对象、哪个区域
变化：看得见、有边界的变化（位置、方向、范围、程度、材质颜色结果）
保留：最容易被误改的高价值事实——在场人数与每人的位置、朝向、持物（逐人点名，不写 everyone）、脸与体形、未变的服装部件、固定地理、道具轮廓、构图机位、光向、未选区域
连续性影响：对应哪个已登记的状态或变体，影响哪些镜头的 frame_refs；没有影响写"无"并说明理由
```

- **每一轮都完整重复保留清单**，只改失败的那一项；只写改动、不写保留，漂移会一轮轮累积（visual-assets §7）。
- **一次编辑只改一组相关的变化**；几处互不相干的修改拆成几次，否则保留清单会失焦。复杂重构改做新变体或新底板。
- **太宽的要求先拆细**："改背景""让她更狼狈"不能直接写成提示词，要落到具体区域和可观察结果。
- **改的是上游事实就不算编辑**：挪门窗、改身份、改道具状态要先改视觉设定（visual-assets §2、§4），不能在编辑提示词里偷改。
- 局部删人这类编辑，变化和保留都要明说：`Remove the man on the right side of the frame completely. Keep every other person, their positions and poses, the background and the lighting exactly as they are.`
- **改机位的链式编辑**（storyboard-keyframes §1 用上一镜末帧出下一镜起始帧）：改的是相机，人和物在世界里不动。先写相机怎么动，再按 video-prompts-general §2b 逐人写他在新画面里的位置；相机换方向后画左画右会跟着变，按轴线算好写死，不写 `same positions`：`Move the camera to the cliff rim, looking back toward the stone path. Keep exactly three people, each once: Gu Changsheng in the grey robe, now on screen-right with his heels on the rim, facing screen-left; Yan Chong in the black robe, on screen-left, facing him; the sword spirit in white, behind Gu's left shoulder, facing screen-left. Keep the light and the single sword in Gu's right hand.` 目检逐个数人头、核朝向，并和上一镜末帧对照有没有被整体镜像。
- 旧图不覆盖：重出改名归档（硬约束 8），refs.json 里记下这次改了什么、为什么。
- 自然语言修订（用户说"工作服换成深蓝，但保留脸和袖口油渍"）自动执行：读当前视觉设定和 refs.json 条目，分清哪些是提示词措辞、哪些要先改视觉设定；改完在 `项目开发/决策记录.md` 记一行改前、改后、保留项、受影响镜头。用户说"更有电影感"这类含糊要求时，不堆风格词，由 art-director 在光比、构图、色彩关系里选一个可观察的方向执行并记录理由。
- 文件被别的会话或人工改过时，先重读当前条目，把两边的有效改动合并，不用旧版本覆盖。

## 5. 参考板的布光：按"要比较什么"选

身份图、道具图默认均匀柔光，因为它们要让下游看清形制；这不是镜头的打光方案（storyboard-keyframes §6b）。需要让某种结构可比较时再换光型：

| 光型 | 让什么可比较 | 压掉什么 |
|---|---|---|
| 均匀正面光 | 五官相对位置、妆面、服色与图案 | 颧骨、鼻梁、下颌的体积 |
| 侧光 / 高位斜侧光 | 骨骼体积与轮廓起伏 | 暗侧细节，并放大不对称 |
| 顶光 | 眼窝、鼻下、颌下的纵向结构 | 暗区里的识别细节与服装层次 |
| 大面积柔光 | 肤质、布料、材质纹理 | 形状边界与轮廓锐度 |
| 小面积硬光 | 金属反射、磨损、工艺痕迹 | 过渡信息，放大瑕疵 |
| 轮廓光 / 逆光 | 外轮廓、发型剪影、服装廓形 | 面部识别，不能单独承担身份图 |
| 场景内实际光源 | 状态图、环境内参考与场景光向一致 | 中性比较条件 |

光型只按"这张板要比较什么"选，不按性别、年龄、贫富或题材映射（"女角一律柔光、男角一律侧光"是模板化，删掉重选）。底光会反转日常明暗读法，身份图不用。

## 6. 文字在参考图里怎么处理

视觉设定里文字有四类来源政策（visual-assets §9）。落到参考图时，本项目只允许三种呈现，因为生成画面不出可读字：

| 来源政策 | 参考图里的呈现 | 写法 |
|---|---|---|
| `exact_readable`（剧情要观众读到） | 后期叠加：承载面留干净 | 写承载面的位置、面积、朝向、材质和受光，让后期贴字有透视可跟；`blank label area, no text` |
| `graphic_only`（只要图形） | 不可辨的图形 | 保留标签、刻痕、徽记的形状和布局，明确 `no legible letters or numbers` |
| `no_readable_text` | 空白 | 承载面保持空白，但材质和结构照画 |
| `pending`（文字未定） | 空白，等剧本补 | 不猜文字；依赖它的镜头先挂起 |

签名、合同条款、账户号这类"剧情必须存在"的文字，参考图里只留承载面；人物"认出签名"的反应靠台词和后期叠字交代，不靠生成的字形。

## 7. 画风只改"怎么画"，不改"画的是谁"

`style_preset` 决定锚点用什么词汇画出来，不决定锚点是什么（styles.md 各节）：

| 可以从画风取的 | 不许被画风改写的 |
|---|---|
| 轮廓简化程度、比例体系（头身比） | 年龄段、体形、面部结构、永久特征（痣、疤）、长期配饰 |
| 线条与表面（线稿、平涂、厚涂、照片） | 造型的组成、变化原因与生效范围 |
| 材质对光的响应、阴影边缘 | 手持道具的归属与文字政策 |
| 主要识别通道（脸、剪影、线条） | 伤、湿、包扎的因果与时间 |
| 背景密度、留白是否作为空间语言 | 入口、路径、固定锚点、楼梯方向、光源来源 |

- 画风以剪影、线条为主要识别通道时，给已有锚点找剪影能承载的写法（发际形状 → 发型剪影的缺口；旧伤 → 轮廓上的缺口；体态 → 肩背重心），不新增、替换或偷偷删掉锚点。
- 留白、两层平涂可以简化装饰，不能简化掉这块底板必须能核对的地理（"入口正对安全门"的关系要仍然看得出）。
- 已有锚点在当前画风下实在画不出来，由 character-designer 选一个可表达的等价锚点，写进视觉设定并记决策记录；不静默改身份。

## 8. 模型差异

模型由用户在 `drama.json` 的 `profiles` 里指定，本技能不替用户选、不擅自换（硬约束 1b）。提示词正文保持模型中立；下面是已知差异，换模型时据此调整写法，而不是调整事实：

| 模型/来源 | 已知行为 | 写法上的对应 |
|---|---|---|
| Qwen-Image-2.1 / Qwen-Image-Edit 系列（中转档位名如 `qwen21`；用哪一档由用户定，写在 drama.json `profiles`） | 能收多张参考，但官方说多图编辑 1–3 张最好；职责重叠的参考会被平均 [官方] | 起始帧默认 2 张、接触镜 3 张（G38）；每张在分工句里点名只控制什么 |
| Qwen-Edit 多角度类用法 | 用"相机转了多少度、站在哪、看向哪"的相机操作句换角度，比笼统"反方向"好控 [社区] | 派生底板、转面板用相机操作句（visual-assets §4） |
| FLUX Kontext 类编辑模型 | 整体改写动词会把人换掉；连续代词会指代混乱 [官方] | 用 change only / replace / remove；用名字或描述性称呼代替 he/she |
| OpenAI 图像模型指南 | 多图时逐张声明职责；多轮编辑每轮重复不变项 [官方] | 分工句逐张写；§4 保留清单每轮完整重复 |
| Gemini 图像生成 | 同一人的多角度参考比单张效果好 [官方] | 背影、侧脸镜可绑裁格参考（§3.3），但不同时绑整张转面板 |
| 中文提示词模型 | 常见做法是在开头加【真人风格，写实风格】这类中文标签 | 本项目参考图提示词固定英文（G18），风格靠 `style` 句；换成只收中文的模型前先在决策记录里说明，并改 G18 的前提 |

- 分隔符、权重语法、模型专用触发词：只有在 `项目开发/模型观察.md` 里同一写法有效 ≥ 3 次后才写进项目规则（SKILL.md 的"先记账再立规矩"）；通用参考不保存这些写法。
- 分辨率、档位属于 `profiles`，不写进提示词正文。
- 换模型后，先挑一条身份图和一块底板重出对照（同提示词），比较身份、比例、空间逻辑三项，结论写模型观察，再决定是否全量重出。

## 9. 自检、反例与改写

写完每条参考图提示词，reviewer（不审自己写的，硬约束 7）逐项给 PASS / REVISE / NOTE，并引用原句：

| 维度 | 问题 | 合格的证据 |
|---|---|---|
| 绑定 | 画的是视觉设定里哪一条、哪个版本 | `subject`/`location` 与视觉设定标题对得上 |
| 区分度 | 去掉名字还认得出、分得开吗 | 稳定锚点 + 当前差异；和同批人物不雷同 |
| 单一用途 | 有没有把互斥需求混在一张 | 用途、构图、状态一致 |
| 空间/尺度 | 关系能同时成立、能复用吗 | 平面图事实、尺度参照 |
| 文字 | 承载面与政策相容吗 | §6 的呈现方式 |
| 经济性 | 有没有重复参考图已承载的内容、堆质量词 | 可删的句子 |
| 越权 | 有没有新造身份、剧情或连续性事实 | 来源与冲突句 |
| 身份污染 | 服装句形制在不在句首、使用痕迹是否超过一处、站姿和脸有没有默认成"侍立""对称娃娃脸" | 遮住名字读服装句得出的身份；§3.1 的面部与排除项 |
| 自足 | 去掉元信息后正文读得懂吗 | 正文不含 ID、路径、流程话术 |

修订要求必须可执行（"补回安全门相对检修台的位置"），不能只写"加强细节""不够电影感"。

反例与改法：

- **混造型、堆质量词**：`A stunning heroine, sometimes in a green work shirt, sometimes in a red gown, hair both short and waist-long, soaking wet but perfectly dry, 8K, masterpiece.` → 两套服装、两种发长、干湿互斥，身份锚点全被套话挤掉。改：绑定一套造型，其余拆成独立变体条目，写回脸型、眉尾缺口这类锚点。
- **文字矛盾**：`A duty logbook whose cover clearly reads "Equipment Review", no text anywhere.` → 可读与禁字同时出现。改：封面留空白承载面，文字后期叠加（§6）。
- **越权编辑**：`Keep everything the same, but turn the repair room into a luxury hotel lobby and move the back door to the left.` → 改的是地点身份和固定地理，还用了整体改写动词。改：先在视觉设定里决定是否新地点，再按新地点写底板。
- **表单直贴**：`Identity: supporting actress. Age/height: 20.` → 字段名进了正文，没有任何可见事实。改：写成自然语言的锚点句。
- **名字对不上**：条目 `subject` 是甲，正文却在描述乙的外貌 → 下游会用乙的脸生成甲。改：正文锚点从甲的视觉设定条目摘。

## 来源

原文只做改写；[官方][社区][推断] 含义同 visual-assets.md。本文件整合了本地短剧资产图片提示词参考（通用配方、人物与造型、地点板、道具板、状态变体、局部编辑、生产参考板、风格帧、审查量表）与资产拆解参考中与出图相关的部分（原套件内容已全部并入，不再需要另读），并按本项目的硬规则（英文提示词、画面不出字、模型由用户定、全自动决策）改写。模型行为的外部来源见 visual-assets.md 与 storyboard-keyframes.md 的来源列表。
