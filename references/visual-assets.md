# 视觉资产：视觉设定、身份图、底板、道具、连续性锁

阶段 D（视觉设定 + refs.json）和阶段 F 的参考图提示词读本文件。来源：本地 `short-drama-assets`（occurrence、identity-vs-variant、continuity-lock、prop-and-state、character-and-look、location-and-view）、`short-drama-image-prompts`（common-recipe、location-plate、prop-plate、edit-and-revision）、`short-drama/references/reference-roles.md`，director 的资产层级与版本纪律，cinematic 的参考图信息预算，实战项目的写法。

## 目录

1. 视觉设定.md 怎么写
2. 身份 vs 变体 vs 镜头瞬态
3. 人物：识别锚点、身高次序、别用模板句
4. 地点：底板地理优先、空场、跨方向同光
5. 道具：身份与状态分开，持物是状态字段
6. 连续性锁与变化记录
7. refs.json 与参考图提示词
8. 参考图的用途与权限
9. 文字政策
10. 自动化规则与硬规则

## 1. 视觉设定.md 怎么写

```markdown
# EP001 视觉设定

一段话：形态、画幅、地点与时代、台词语言、后期叠加规则、生成画面不出字。

## 项目视觉方向（本剧共用）
- 稳定项：质感、镜头、光线、皮肤、构图（人物不看镜头）
- 色彩：日常色调；保留给后期叠加的专属颜色（例如全剧唯一的强红留给印章字）
- 失效信号：出现就算错的东西

轴线（每场）：谁坐哪一侧面朝画左/画右；各人的镜头用哪块底板。

## 人物 · 遥
- 画面代称：Haruka（英文正文里用的拼写；正文不点名写「无」）
- 识别锚点：年龄、职业；正面、侧面、背面各至少一条可见锚点；以 `参考图/IMG-HARUKA.png` 为准
- 本集造型：服装、鞋、饰品（会跨集变的另开变体）
- 音色：a young woman's calm, clear voice（写进 refs.json 的 voice，全剧一致）
- 状态：本集里会发生什么可见变化（湿发、伤、换衣）

## 地点 · 会议室
- 识别锚点：入口、固定陈设、材料、光源方向；画左画右各是什么
- 状态：日 / 夜 / 停电（要跨镜持续的状态才新建底板版本）

## 道具 · 红笔与方案
- 识别锚点：形制、材料、尺度
- 状态：谁持有、哪只手、位置、开合、内容、文字
```

逐段问六问抽取出现：谁、以何种方式出现（画内/画外声/被提及）、此刻可见什么、必须实现什么、为何重要、从哪来到哪去。推测不能冒充可见事实；"她"没有唯一先行词就回剧本消歧，不在资产阶段猜。

## 2. 身份 vs 变体 vs 镜头瞬态

三问：去掉临时状态后是不是同一个 → 是则复用；下游要不要区分可复用状态（换装、受伤、湿身）→ 要则新变体；地理或功能真变 → 新资产。机位、站位、视线、左右手归分镜，不建资产。双胞胎和冒名者是新人物，伪装和年龄段是造型版本。

## 3. 人物

- **识别锚点必须可见可比较**：脸型、发际线、发型剪影、体形、标志性配件；侧面、背面各至少一条（很多镜头只给侧脸背影）。
- **全组身高次序**写进视觉方向："三上最高，遥比他矮约半个头"；正反打机位高度靠它。
- **易混角色逐条枚举可见差异**，至少两个通道不同（发型剪影、服装主色、体形）；同批人物板并排读，删掉逐字重复且与角色无关的模板句（"九头身、修长双腿"）——模板句会把所有人拉向同一张脸（G20 查提示词相似度）。
- **人物关系不决定美丑**："出身普通、被轻视"不等于长相平庸；憋屈期的主角也按商业主角的吸引力写。
- **身份图只画常规干净状态**：素背景、正面、全身、中性表情、无字；不带以后要消失的饰品（金表、戒指、金链会跟着人物走遍全剧，G18 警告）；血迹、湿发、战损是按镜绑定的状态，不进基础卡。
- **先抽卡后派生**：换装、受伤、多视图都以已确认的身份图为图生图输入，只写变化部分；用文字重新生成身份就会换人。
- **音色**：每个说话角色一段固定音色描述（年龄性别、音色、音区、语速、默认情绪），写在 refs.json 的 `voice`，视频提示词逐字带（G21）。首帧模式不能挂参考音频，这是保持逐镜音色一致的唯一办法。

## 4. 地点

- **底板地理优先**：从哪个方向看、入口在哪、固定锚点、两两关系、视线终点，然后才是氛围。写清画左画右各是什么，轴线才有依据（G19）。
- **默认空场**：底板不放关键人物（人会固化站位）；`No people`。
- **按状态分版本**：昼/夜、开灯/停电、雨要跨镜持续才建新版本；临时烟尘、人群写进视频提示词。
- **跨方向同光**：同一地点同一时段的各方向底板共用主光来源、色温关系、光比方向（正反打两块底板单看都好看、剪在一起像两个时间，是常见返工）。
- 一场戏用两块底板：窗一侧、投影一侧，分别给两边人物的镜头。

## 5. 道具

- 身份：尺度（手持级/桌面级/家具级）、形制、材料、功能、永久标记。
- 状态：负责人、持有人、哪只手、位置、开合、内容、可读文字。打开匣子不新建资产，只改状态；同款多件会被交换时分开建身份。
- 内容物和人物知情是两条连续性：盒里有东西不等于人物已经知道。
- 道具图：白底/素底、无手、带尺度短语（G19）。

## 6. 连续性锁与变化记录

**锁**：跨镜不变、观众看得出的可见事实，写成最小名词短语，逐字带进范围内每条起始帧提示词（G23）。上锁三条件：≥2 镜出现；观众看得出不一致；不随剧情改变。锁面 = 颜色 + 材质/形制 + 物体，不含动作、状态、镜头词；一集通常个位数。

```jsonc
// shots.json 顶层
"locks": [{"id": "LOCK-BLAZER", "phrase": "charcoal grey blazer", "subject": "遥", "shots": "all"},
          {"id": "LOCK-WATCH", "phrase": "gold wristwatch", "subject": "三上", "shots": ["EP001-S03", "EP001-S07"]}]
```

**变化记录**（写在视觉设定的"状态"和剧本 `[连续性]`）：前态、后态、原因（场次）、生效范围、受影响的镜头。**未知 ≠ 恢复默认**：最后一次明确的状态一直有效，直到剧本明确改变；没提伤不等于伤好了。伤妆、湿衣、停电最容易被模型自动复位，靠锁和变化记录挡。

## 7. refs.json 与参考图提示词

```jsonc
"IMG-HARUKA": {"kind": "identity", "subject": "遥", "name": "遥 全身身份参考",
               "controls": "脸、低马尾、体形", "not_controls": "服装、姿势、表情、背景",
               "voice": "a young woman's calm, clear voice",
               "profile": "krea2_turbo", "res": "2K", "refs": [],
               "prompt": "Photorealistic full-body photo of one slim Japanese woman about 28 standing against a plain light grey studio wall, facing the camera, calm neutral expression, shoulder-length black hair in a low ponytail, a charcoal grey blazer over a white shirt, dark trousers, flat shoes. Real unglamorous skin, soft even light, no text, no logo."}
"IMG-PLATE-MEETING": {"kind": "plate", "location": "会议室", "prompt": "Photorealistic empty location plate, candid 35mm film still, daytime: a corporate meeting room, a long table running toward a projection screen at the far end, floor-to-ceiling windows with flat white daylight on the left, a plain white wall with a projector on the right. No people. No logos, no readable text anywhere. Realistic colors, subtle film grain."}
```

提示词八段顺序：用途与主体 → 稳定锚点 → 版本差异 → 构图与尺度 → 材质色彩光 → 背景/空场 → 文字与功能 → 排除与保留。正文不带 JSON 键名、权重语法、模型控制词；审美词落到可观察的选择；不假精确（来源写二十多岁就不写 23 岁）。

起始帧提示词的参考图分工句（实战验证过的写法）：`Picture 1 sets only the location and the lighting, as a soft out-of-focus background; do not copy any person from it. Picture 2 sets only the person's identity: keep exactly her face, hairline, skin and build; her pose, expression, clothing, framing and action follow this description, not Picture 2.` `frame_refs` 的顺序就是 Picture 编号。

## 8. 参考图的用途与权限

一张参考图只回答一个问题，用途九选一：身份 / 造型状态 / 地理 / 构图 / 尺度 / 效果 / 起始帧 / 结束帧 / 风格。每张写可以控制什么、不能控制什么。起始帧只锁开场构图与姿态，不锁整镜。负面词擦不掉参考图已有的像素：参考图里有字、有水印、多一个人，就重出，不在提示词里写 "no watermark"。

## 9. 文字政策

剧情要求的文字分四类：exact_readable（合同抬头、账户尾号）→ 后期叠加或可读；graphic_only → 只有图形（地滑立牌只有图标）；no_readable_text → 空白；pending → 回剧本补。生成画面里默认不出任何可读文字，日文字形一律后期；手机屏幕背对镜头或朝下。readable 与全局禁字不能同时出现。

## 10. 自动化规则与硬规则

自动判定（不问人）：年龄段按角色功能；易混角色至少两个可见通道不同；变体按第 2 节三问；现实品牌默认虚构化；缺字回剧本补，补不出就后期预留。

硬规则：不猜身份（含混指代退回剧本消歧）；不静默降级为文生视频（缺图就等出图）；锁面逐字携带；提示词阶段不改写身份、地理、剧情状态；readable 与禁字互斥。
