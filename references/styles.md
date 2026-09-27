# 风格库：七种画风的写法

阶段 A 定风格（写 `drama.json` 的 `style_preset` 和 `style`），阶段 D 写身份图与底板、阶段 E 写起始帧与视频提示词时读本文件。来源：原本地套件的六张制作形态卡（实拍、二维动态漫、风格化三维、水墨笔触、Q 版表达、国漫二次元，已并入 §1b 与 §13）、题材卡（仙侠修真、古装权谋）、漫剧关键帧词表、H3 与 Seedance 方言，以及本 skill 的 [4-分镜与视频提示词.md](4-分镜与视频提示词.md) 与 `按一下回到十秒前` EP001 复盘。标注：**[自测]** 本项目实测；**[套件]** 本地 skill 已有结论；**[推断]** 由多条来源推出、未在本项目实测。

## 目录

1. 怎么选、怎么锁：`style_preset` 与 `style`
2. 所有风格共用的底线
3. `live_modern` 真人现代都市（默认）
4. `live_period` 真人古装 / 宫廷
5. `live_xianxia` 真人修仙仙侠
6. `anime_cel` 日系动漫（赛璐璐）
7. `guoman_3d` 国风动漫 / 3D 国漫修仙
8. `manhwa` 韩漫 / 条漫风
9. `cg_realistic` 写实 3D / CG
10. 视频后端的差异
11. 风格审查问题
12. 系统面板主题预设（后期叠加的弹窗、面板、卷轴）
13. 制作形态卡：每种画风额外要写的字段（含水墨、Q 版、混合形态、异质身体）

另：§1b Look Development 试镜（定画风前怎么比、怎么记）。

## 1. 怎么选、怎么锁

`drama.json` 里两个字段一起写：

```jsonc
"style_preset": "live_xianxia",   // 七选一：live_modern | live_period | live_xianxia | anime_cel | guoman_3d | manhwa | cg_realistic
"style": "Cinematic live-action Chinese xianxia drama still, …"   // 起始帧、身份图、底板共用的风格句，从下面对应一节的「风格句」整句复制，只按本剧改颜色和时代
```

- **怎么选**：先看题材，再看预算和后端。都市打脸、职场、校园、豪门默认 `live_modern`；朝堂、宅斗选 `live_period`；修仙、宗门、御剑在真人和动画之间选——要"像电视剧"选 `live_xianxia`，要大场面法术、飞行、群战而且不怕观众觉得是动画，选 `guoman_3d`；点子来自日系轻小说、校园异能选 `anime_cel`；来自韩国条漫、复仇重生、霸总爽文，要竖屏精修脸选 `manhwa`；要科幻、末日、怪物、机甲又想保留写实质感选 `cg_realistic`。判不出选 `live_modern`，写进决策记录。
- **全剧锁定一种**：立项定下后，全剧所有身份图、底板、道具图、起始帧都用同一句 `style`，不在单集、单场、单镜里换风格（回忆、梦境也不换；需要区分就改色调和光，不改画风）。中途确实要换，只能整剧回到阶段 D 重出全部参考图，写进决策记录。
- **风格句只放一次**：起始帧提示词的结尾 `Style: …` 就是 `drama.json.style` 原句；分镜里不再堆别的风格词。风格句和视频头句只写画风质感和实时速度，不写运镜许可和特效、大气词（粒子、雾、体积光）：写进全剧固定句，就等于每一镜都许可了运镜和特效；需要时只在那一镜正文写（video-prompts-general §2b 一）。下文各画风关键词里的这类词同理。风格词不能顶替身份、地理、尺度、构图事实（[套件] 漫剧关键帧词表：事实先于审美词）。
- **视频提示词也要带风格**（只锁起始帧不够）：图片用 `style`，视频用下表的"视频保持句"，两句互不替代。视频保持句只点名"整条镜头必须保住的画面质感"和拒绝项，不复述首帧里已经画出的外观。做法：立项时按画风选下表的视频头句，把视频保持句接在它后面，一起写进 `drama.json` 的 `video_prompt_head`，全剧不变。**非真人画风的头句和保持句只以本表为准**（video-prompts-h3 §9 只引用本表，不另写一份）。`4-分镜与视频提示词.md` §9 的实战头句（realistic human behaviour）**只适用于 live_* 和 `cg_realistic`**；非真人画风写这个词（以及 handheld），会把动画往真人方向拉。任何画风的头句都不写运镜和特效词（G36）。[官方][社区]

  | preset | 视频头句（接在 `integrated_multimodal_description: [Shot 1]` 之后） | 视频保持句 |
  |---|---|---|
  | `live_modern` | 沿用 video-prompts-h3 §9 实战头 | `Real skin keeps its pores and texture throughout; faces never smooth over, morph or flicker.` |
  | `live_period` | 同上 | `Silk and brocade move with real weight; candle and window light stay warm and motivated; faces keep real skin texture throughout.` |
  | `live_xianxia` | 同上 | `Live-action drama look throughout; the magic glow stays restrained and lights nearby faces and surfaces; faces never morph.` |
  | `cg_realistic` | 同上 | `Photoreal film-VFX look throughout; heavy objects move with weight; no game-cutscene smoothness, no rubbery motion.` |
  | `anime_cel` | `Single continuous take, no cuts, no transitions, starting exactly from the opening frame. Real-time animation timing: short holds between key poses, eyes blink, the mouth moves in simple shapes with the words, hair tips and clothing edges sway. No subtitles, captions or on-screen text at any time.` | `The whole take stays a 2D TV-anime frame: constant thin ink outlines, flat cel colours with one hard shadow layer, painted background unchanged; it never turns 3D or photographic.` |
  | `manhwa` | `Single continuous take, no cuts, no transitions, starting exactly from the opening frame. Real-time speed. Only small refined movements: hair strands, eyelashes and fabric edges move, the mouth moves in simple shapes with the words. No subtitles, captions, speech bubbles, panel borders or on-screen text at any time.` | `The whole take stays a polished webtoon illustration: thin clean line art, soft gradient shading, luminous skin; no speech bubbles or panel borders appear.` |
  | `guoman_3d` | `Single continuous take, no cuts, no transitions, starting exactly from the opening frame. Real-time animation timing. Stylized 3D character animation with weighty body mechanics; hair strands and silk layers follow every movement. No subtitles, captions or on-screen text at any time.` | `The whole take stays a stylized Chinese 3D animation frame: individually rendered hair strands, layered silk, consistent rim light; it never turns photographic or flat 2D.` |

- **起始帧镜头词按画风换**：动漫类（`anime_cel`、`manhwa`）不写焦段、bokeh、cinematic lighting、volumetric、4k 这类摄影与渲染词，它们会把 2D 拉成 3D；具体写法见 [4-分镜与视频提示词.md](4-分镜与视频提示词.md) §6b 第 8 项的补充说明。[社区]
- **题材色调（可选，与画风正交）**：悬疑、赛博朋克这类题材改的是光、色和环境动态，不是渲染方式，不新增 preset。需要时把下面一句接在 `style` 句的色彩部分，和 `style` 一起全剧锁定。[社区][推断]
  - 悬疑惊悚：`one hard visible light source, deep shadows yet faces and clues stay readable, cold desaturated palette, high contrast`。镜头多用慢推、证据特写，手持只给慌乱的时刻；环境动态写灯管闪一下、门缝影子移动、滴水。最常见的翻车是太暗、脸和证据看不清。
  - 赛博朋克：`neon glow from off-frame signs in cyan and magenta, wet reflective ground, thin rain, signs carry only abstract shapes`。主色只用两种，第三种只给强调物；环境动态写雨丝、全息广告闪、井盖冒蒸汽。霓虹不能把脸染到认不出，招牌不出字。
- **风格定下前先各试一镜**：候选画风在 H3 上各出 1 张起始帧 + 1 条 5 秒视频，看画风在视频里保不保得住，再锁定；决策记录写试镜文件路径和每条视频从第几秒开始漂（没漂写"全程保住"）。没有授权出试镜时写"未试镜"，不写"已验证"。"非真人画风在 H3 上会往真人漂"目前是推断，MiniMax 自述 Hailuo 2.3 起加强了动漫、水墨类风格，以本项目实测为准。[官方][推断]
- 机械门：`style_preset` 没写或不在七个值里报 G33（warn）。

## 1b. Look Development 试镜：把画风变成可比较的代表帧

上面"风格定下前先各试一镜"的展开做法。Look Development 不是给全剧贴一个风格标签，也不是让参考图接管人物和剧情；它把候选画风写成少量可观察的规则，出几张代表帧比一比，再锁定。

**什么时候值得做**（不是每部剧的必经阶段；已经确定用某个 preset 且没有下面的疑问，直接锁定即可）：
- preset 已选，但材质、光色、线条边缘、画面密度还停在形容词；
- 身份图、底板、起始帧各自成立，放在一起却不像同一部作品；
- 某种画风适合静态设定图，但不确定它在冲突场里还保不保得住表演、身份锚点和层次。

**每个候选方向先写四项**（写进 `项目开发/决策记录.md` 或系列简报的画风一节）：
- **稳定项**：跨人物、地点和冲突场都必须保留的形状语言、材质处理、色彩层级、阴影边缘、景深倾向、画面密度；
- **可变量**：允许按场次变的冷暖、对比、留白、光比、运动层；
- **叙事职责**：这些选择帮观众认出什么、感到什么；
- **失效信号**：可观察的风险，例如身份锚点被氛围吃掉、群像层级打平、冲突场只剩氛围。

自检：把风格名删掉后，如果材质、光、色、边缘和空间的写法一个字都没变，这个方向还只是标签，先补具体写法再试。

**比哪几类代表帧**：按本剧风险选一类或几类，不固定宫格数、帧数和景别比例。
1. 人物表现帧：身份锚点、肤质或线条、视线与细小表演是否还能读；
2. 核心地点帧：空间层级、材质对光的反应、光源逻辑是否可复用；
3. 高压力场景帧：这种画风能否承载遮挡、冲突与注意中心，而不只适合静态展示。

**权限边界**：代表帧里的风格参考只控制色彩层级、材质处理、阴影边缘、景深和画面密度，不能控制角色身份、场景地理、剧情状态、道具文字和信息揭示（visual-assets §8 的"风格"用途）。人物帧仍绑准确的身份图，地点帧仍绑准确的底板；风格帧不能反过来改写视觉设定或剧本。

**自动决策与授权**：选哪些候选、比哪类帧、最后锁哪一个，由导演岗按上面四项和本剧题材自己定，写进决策记录（选了什么、放弃了什么、依据哪张代表帧）；不停下来问用户。但出代表帧会花生成的钱，只能用用户已指定的模型与档位（硬约束 1b），计入本轮已授权的提交次数；没有授权的生成条件时，只写候选规则，先按 §1 默认 preset 推进，出图留到授权后。锁定的是可观察的视觉规则和对应的 `style` / `video_prompt_head`，不是某个模型名或某次生成结果。某次代表帧的观察只对这个项目、这组提示词和参考图有效，记进 `项目开发/模型观察.md`，不当成模型的普遍规律。

## 2. 所有风格共用的底线

不管哪种画风，下面几条都不放松，写在各风格规则之前：

1. **比例真实**：人物和环境的比例按现实世界（护栏到腰、门比人高约 1.2 倍、一级台阶约 17 cm），动漫、Q 版也只改头身比，不改环境尺度。写法见 [3-视觉设定与图片.md](3-视觉设定与图片.md) §12。
2. **场景合理**：门后不接门、下楼的楼梯不接上楼的楼梯、窗外景和楼层一致。见 visual-assets §4b。
3. **环境运动按需**：自然存在或承担情节时写清；静止本身不判失败。见 4-分镜与视频提示词.md §6。
4. **台词有情绪**：每句写 `emotion`（情绪·强度·语速·音量）。见 [2-剧本.md](2-剧本.md) §4b。
5. **生成画面不出字**：动漫的拟声字、修仙的符箓文字、韩漫的对话框一律不让模型画，后期叠加或做成无字图形。视频提示词同样写 `No subtitles, captions or on-screen text at any time`，日漫、韩漫的视频保持句再写 no speech bubbles、no panel borders——视频模型不写拒绝项时会自己加字幕和转场。[社区]
6. **因果可见**：法宝、援兵、异象第一次出现前要有铺垫镜（`setup_for` / `requires_setup`，G32）。
7. **远景不给正脸**：全景、远景里的主要人物用背影、后四分之三侧或侧剪影，正脸只在中近景和特写给；远处的小正脸最容易崩脸、换脸（H3 官方仙侠示例也这样处理）。[官方][自测]
8. **风格句带"邻近画风排除"**：每种画风最容易混进哪两三种邻近画风，就在风格句里点名排除（下面各节风格句已写好）。只排除邻近的，不堆长串负面词。[社区]

## 3. `live_modern` 真人现代都市（默认）

**适用题材**：都市打脸、职场、校园、豪门婚恋、家庭、悬疑、异能（金手指是小装置而非大特效）。

**画面语言**
- 色彩：日常自然色、低饱和；全剧留一个专属强调色给后期叠加（例如印章字的红），画面里不出现同色大面积物件。
- 光：实景可见光源（窗、日光灯、台灯、路灯），写明方向；夜戏有一个明确的主光源，不要满屏补光。
- 构图：中近景为主，人物偏一侧，另一侧留空给叠字；背景有纵深（走廊、窗外、远处的人）。
- 镜头节奏：平均镜长不低于 2.5 秒（storyboard-keyframes §7c），憋屈段慢、反击段快；同一个人的连续戏用一个长镜头（§7b）；运镜轻微手持，兑现那一拍一次慢推。

**角色造型与比例**：亚洲真人比例，成人 7–7.5 头身；高中生男 165–180 cm、女 155–165 cm（写进身份图，见 visual-assets §12）。服装写颜色 + 材质 + 款式；校服、工牌去掉可识别标识。

**风格句（直接进 `style`）**

```text
Candid 35mm film still from a live-action TV drama, shot on location, available light only, shallow depth of field, natural film grain, muted realistic colors, real unglamorous skin with visible pores and fine lines, natural uneven skin tone, true-to-life human proportions, nobody looks at the camera, not a studio portrait, no beauty filter, no airbrushed or waxy skin, not 3D rendered, not anime, no text, no logos, no watermark.
```

关键词：`live-action TV drama still`、`shot on location`、`available light`、`35mm`、`natural film grain`、`real skin texture`、`true-to-life proportions`。

**视频提示词写法**：动作写日常可演的动词（推、抢、递、坐下、站起、把纸推过去）；表情写肌肉动作并带否定限定（video-prompts-general §5）；运镜默认锁定，憋屈、被围这类要不稳感的镜在正文写 `subtle handheld drift`；环境动态写路过的人、日光灯闪一下、窗帘被风吹、空调出风吹动文件角。

**声音与台词腔调**：日常口语，短句，被抢被打当场出声；配音情绪真实但不播音腔，喊叫句要喊出来（不是提高音调念）。

**禁忌与常见翻车**：
- 人比护栏矮一截或和护栏一样高（EP001 教训）——身份图和起始帧都写尺度锚点。
- `smirk / grin` 被演成开心的笑 [自测]。
- 底板台阶方向与剧情相反 [自测]。
- 背景空无一人、完全静止 [自测]。
- 过度美颜、磨皮、网红脸：写 `real unglamorous skin`，不写 `beautiful`、`flawless`。

**后端注意点**：推镜会糊，需要推近的镜起始帧直接出到推完的景别 [自测]；H3 的 50 步档（实测项目用的档位；用哪一档按 drama.json `profiles`，由用户定）台词口型最好但动作容易偷懒，动作写在第一拍；Seedance 写中文自然指令、用 `@图片1` 逐项声明参考职责，时间段用整数秒 [套件]。

## 4. `live_period` 真人古装 / 宫廷

**适用题材**：古装权谋、宅斗、宫斗、复仇、替嫁、女官升职。

**画面语言**
- 色彩：按朝代定主色（宫廷正红、明黄、青绿；民间灰褐、靛蓝），全剧一张色卡；妃嫔等级靠衣色和饰物区分，写进视觉设定。
- 光：日景柔光从窗格透入、有窗棂投影；夜戏烛光、灯笼，主光暖色且来源可见（案上的烛台、廊下的灯笼），不要现代补光的平光。
- 构图：对称构图表现礼制和压迫（大殿、正厅），跪拜镜用俯角；私下密谋用前景遮挡（屏风、帘子）。
- 镜头节奏：比都市慢半拍；礼仪动作（跪、叩首、还礼）完整拍完再切，不剪一半。

**角色造型与比例**：真人比例；发髻、冠、步摇会加高头部轮廓，身高锚点写"不含发髻"；衣摆拖地的写清长度（`hem brushing the floor`）。朝服、常服、寝衣分开建造型变体。

**风格句**

```text
Cinematic still from a live-action Chinese historical costume drama, practical sets with carved wooden lattice windows and real fabrics, soft natural window light or warm candlelight from visible sources, shallow depth of field, subtle film grain, rich but realistic period colors, true-to-life human proportions, nobody looks at the camera, not a studio set, no modern objects, no plastic sheen on fabrics, not 3D rendered, not anime, no text, no calligraphy, no seals, no watermark.
```

关键词：`live-action Chinese historical costume drama`、`practical set`、`carved lattice window`、`silk and brocade`、`candlelight from a visible candle`、`period-accurate`。

**视频提示词写法**：衣料是最好的环境动态（`her long silk sleeve sways as she turns`、`the bead curtain swings and clicks`）；宫灯晃、烛火跳、香炉青烟飘、廊下宫女低头走过（远、虚、少）。行礼动作拆成起势—下跪—叩首—起身，一镜一段。

**声音与台词腔调**：半文半白，以白话为骨、少量书面词点缀（"本宫""奴婢""回禀"），一句里文言词不超过两个，观众听一遍能懂；配音语速比都市慢一档，威胁句压低声音、不吼。

**禁忌与常见翻车**：
- 牌匾、对联、圣旨上的字被模型画成乱码——写 `plain lacquered board with no characters`，内容后期叠加或靠台词。
- 服饰朝代混搭（明制袄裙配清代旗头）：视觉设定写死朝代与形制；原著没明说时怎么推断、架空怎么写，见 visual-assets §1 时代基准。
- 室内太亮太平像影棚：写明光源实物。
- 殿内空间不合理（门后又是门、台阶方向乱）：见 visual-assets §4b。

**后端注意点**：宽袖、长发要在正文里写清随动作怎么摆，支持负向提示词的模型加 `cloth clipping`；H3 注意发饰在转头时漂移，起始帧和视频正文都写清发饰；Seedance 写中文服饰名更准（"马面裙""交领右衽"）[推断]。

## 5. `live_xianxia` 真人修仙仙侠

**适用题材**：修仙、宗门、废柴逆袭、重生复仇、师徒、御剑。

**市场提醒**：2026-09 红果 AI 真人剧榜里没有一部修仙，修仙赛道几乎全是 3D 漫剧；真人修仙能做成系列的，靠的是"现代场景 + 古人身份"的反差（客厅、医馆、祠堂），不靠特效仙界。要大场面修仙、打算续季的，优先 `guoman_3d`（[market-hits.md](market-hits.md) §4.6）。

**画面语言**
- 色彩：清冷基调（青、白、雾灰）+ 每个流派一种法术主色（剑修冷蓝、丹修暖金、魔修暗紫），全剧法术色卡写进视觉设定，不同人的法术颜色不能撞。
- 光：自然光打底（山间薄雾、晨光、洞府的石壁反光），法术是**画面里的第二光源**——要写法术光照亮了谁的脸、在地面投出什么颜色。
- 构图：大场面用远景交代山门、云海（不配台词）；斗法用中景看清两人位置和法术来去方向；感悟、突破用近景加粒子。
- 镜头节奏：日常戏像古装剧；斗法快切，一镜一个法术动作（插入镜短于 1.5 秒要写 `fast_cut_reason`）；渡劫、突破给一个 8–15 秒长镜。

**角色造型与比例**：真人比例（不做动漫长腿）；仙门服饰长袍宽袖，写清颜色、层数、腰带；境界若绑造型（发冠、衣色、瞳色），台阶在立项时定死。剑、法器按道具建资产，写尺度（`a straight sword about 1 metre long`）。

**风格句**

```text
Cinematic still from a live-action Chinese xianxia fantasy drama, real actors in layered flowing robes, mountain sect architecture, soft diffused natural light, any magic glow stays restrained and practical-looking and lights nearby faces and surfaces, shallow depth of field, subtle film grain, true-to-life human proportions, nobody looks at the camera, not a video-game render, not 3D animation, not anime, no plastic skin, no text, no talisman characters, no watermark.
```

关键词：`live-action xianxia drama`、`flowing layered robes`、`drifting mist`、`spirit light`、`glowing particles`、`restrained VFX`、`magic glow casts colored light on`。

**视频提示词写法：法术怎么写才动得起来**
- **法术三拍**：起势（结印、并指、剑指掠过剑身）→ 生效（光从哪里出、往哪个方向走、多快）→ 后果（照亮了什么、吹动了什么、打中了什么）。只写"施法"模型会让人站着发光。
- **御剑**：`the sword lifts from its sheath and hovers level at knee height; he steps onto the blade, his robe hem snaps in the wind as the sword carries him forward and up toward screen-right`。一定写起飞方向、离地高度、衣袍被风吹的方向；远景起飞、近景只拍衣袍和脸。远景版用背影或后四分之三侧（`seen from behind, a small figure rising on the sword toward screen-right, a thin pale-blue trail behind him`），上面这句留作近景版。[官方]
- **灵气粒子**：`faint pale-blue motes drift upward from the ground and spiral slowly around her hands`——写颜色、密度（faint / a few）、运动方向（upward、spiral、toward his palm），不写 "magical energy"。
- **法术光效**：`a thin line of cold blue light runs along the sword edge from hilt to tip, then flares once; the light flickers across his face and the stone floor`——写光源位置、传播路径、它照亮的表面。
- **冲击后果**：地面裂纹、碎石溅起、树叶倒伏、旁人衣袍被吹向同一方向、烛火一齐倒向一侧——后果比光效更能让观众相信"力量"。
- **受力写法与特效数量**：起势写重心和发力点（`his weight sinks onto the back foot, two fingers slide along the flat of the blade`）；生效只写**一个核心特效**（剑光或气浪），辅助特效最多一个（残影或飘尘）；后果至少写两处环境受力，并写光照亮了哪个表面。一镜塞多个特效，模型会丢掉或打乱其中几个（和 EP001 一镜多动作被丢是同一个问题）。[社区][自测]
- **较稳的仙侠镜头类型**：御剑穿云的远景背影、突破时脚下灵气升成光柱、月下对剑落花、丹炉点火照亮脸。[社区]
- **环境常驻动态**：云雾流动、檐角铃铛摆动、瀑布、落花、道袍衣带飘。

**声音与台词腔调**：文白夹杂的度——称谓与术语用古风（"师尊""弟子""道友""筑基""结丹"），叙事和情绪用白话；一句里术语不超过一个，第一次出现的术语要在同场用白话解释一次（"筑基——就是能御剑了"）。法术音效后期做：蓄力的低频嗡声、出剑的破空声、命中的闷响；配音念法诀时压低、稳，不要唱腔。

**禁忌与常见翻车**：
- 符箓、阵法、剑上刻字被画成乱码：写 `blank yellow paper talisman with abstract red strokes, no readable characters`。
- 法术光把整张脸吃掉、认不出人：写 `the glow stays below her chin, her face remains clearly lit by daylight`。
- 光效没有光源方向，像贴上去的：写它照亮的表面。
- 远景御剑人物比山门大：写尺度（`a tiny figure against the 30-metre gate`）。
- 境界数字、特效越堆越多但没冲突（仙侠修真题材卡：特效是成本黑洞，用余波承载）[套件]。

**后端注意点**：H3 光效偏弱、容易静止，特效镜在 H3 上改成"后果镜"（碎石、风、他人反应）；Seedance 可以用中文写"剑身泛起冷蓝色光，从剑柄流向剑尖"，时长 ≥ 5 秒才放得下三拍 [推断]。支持负向提示词的模型加 `glowing text, runes, symbols`，防止模型自己加符文字。

## 6. `anime_cel` 日系动漫（赛璐璐）

**适用题材**：校园异能、恋爱喜剧、轻小说改编、异世界、日常搞笑、日语台词的剧。

**画面语言**
- 色彩：平涂色块 + 一到两层硬边阴影；背景是写实度低一档的手绘背景（这个差档要在视觉设定里声明，否则人物像贴纸）[套件 国漫二次元]。
- 光：主光方向明确，脸上高光与阴影的落位逻辑全剧一致；逆光用轮廓光（rim light）。
- 构图：人物偏一侧，大量天空、教室窗景；情绪特写可以用背景虚化成色块或速度线（速度线后期加，不让模型画）。
- 镜头节奏：定帧 + 局部动（眨眼、口型、发梢）撑对白，情绪转折镜给全动作 [套件 国漫二次元运动预算]。

**角色造型与比例**：头身比 6–7（高中生约 6.5），全剧固定；**只改头身比，不改环境尺度**——护栏仍到腰、门仍比人高约 1.2 倍。识别靠可枚举的结构差异：发型剪影、发色、瞳色与高光形状、一件不摘的配件；同剧角色逐条列差异，防止互相趋同 [套件]。

**风格句**

```text
Japanese TV anime style frame, clean cel shading with two-tone hard-edged shadows, flat color fields, constant thin ink outline of even weight, soft painted background slightly less detailed than the characters, clear directional light with consistent highlight placement, consistent head-to-body ratio of about 6.5, environment drawn at real-world scale, nobody looks at the camera, not 3D rendered, not thick-paint illustration, not photographic, no volumetric light, no text, no speech bubbles, no sound-effect lettering, no watermark.
```

关键词：`TV anime frame`、`cel shading`、`crisp line art`、`flat colors`、`hard-edged shadow`、`painted background`、`rim light`、`consistent character design`。

**视频提示词写法：表情符号化与口型**
- **表情符号化**：动漫的情绪靠可识别的符号动作，写具体形状：`her eyes turn into wide white circles for half a second`（震惊）、`a large sweat drop slides down the side of his head`（尴尬）、`his cheeks flush with diagonal pink lines`（害羞）、`her shoulders shoot up and her hair bristles`（炸毛）。一镜只用一个符号，不叠。
- **口型**：动漫口型是开合几档，不是真人唇形；写 `simple anime mouth flaps in time with speech, three mouth shapes, eyes blink once`；不写 `realistic lip sync`（会生成出真人唇部，画风崩）。
- **动作**：少帧感的动作要写"停顿 + 爆发"：`he freezes for half a second, then snaps his head toward screen-left`（写具体时长不写 beat；台词句中句后不写停顿，E31）。
- **环境动态**：窗外云慢慢移、樱花瓣飘、窗帘鼓起、黑板前粉笔灰、远处操场上奔跑的小人（虚、少）。
- 头部、发型在转头时不变形：目标模型支持负面提示时，负向加 `off-model face, inconsistent line thickness, morphing hair`（H3 没有负面通道，不加）。

**声音与台词腔调**：配音夸张度比真人高一档——惊叫、吐槽、撒娇都要明显（日系动漫配音的"声优感"），但喊叫句仍要落在台词情绪上，不是全程高亢；拟声（「ドキッ」「ガーン」）不让模型画字，后期叠字或做音效。语速可比真人快 10–15%。

**禁忌与常见翻车**：
- 画风在镜间漂移（这镜赛璐璐、下镜厚涂）：全剧用同一句 `style`，并在身份图上确认。
- 模型自己画拟声字、对话框：风格句写 `no speech bubbles, no sound-effect lettering`。
- 人物被画成 8 头身长腿、坐在教室里比课桌高一截：写头身比和尺度锚点。
- 手指数错、手形崩（动漫最常见）：细节清单逐张查手。

**后端注意点**：动漫风格容易往 3D 化或真人漂，支持负向提示词的模型加 `3d render, photorealistic`；H3 以真人训练为主，动漫口型可能出真人唇 [推断]，对白多的动漫剧先做一镜对照再定后端；Seedance 在提示词开头写"日式赛璐璐动画风格"，并用 `@图片1` 锁角色设定图 [推断]。

## 7. `guoman_3d` 国风动漫 / 3D 国漫修仙

**适用题材**：修仙、玄幻、神话改编、宗门争霸、大场面斗法；对标国产 3D 动画番剧的质感。

**市场依据与续季打法**（[market-hits.md](market-hits.md) §4）：红果漫剧榜头部是 3D 修仙和团宠续季；**3D 优于 2D**——同一个倒练功法设定，3D 版出到第 4 季，2D 版两季后下滑，所以修仙不要选 2D 平涂。续季按"每季一个境界或一张地图"切分，每季开头用同一句 `style` 重新校准全部角色身份图，保证跨季人物一致（漫剧口碑的吐槽集中在表情生硬和更新慢）；形态进化、数值计数器、图录点亮是最好拍的升级可视化，面板和计数器一律后期叠加（§12）。打脸层级的最高层用虚构神系，不画真实宗教的神佛本尊（market-hits §4.5 禁区）。

**画面语言**
- 色彩：高饱和但有主色调（冷青云海、暖金宫殿）；氛围色可以很浓，但**不得吃掉人物识别色**（瞳色、发色、衣色）[套件 国漫二次元]。
- 光：体积光、丁达尔光、边缘光、法术自发光；每个画面写光源色 + 反射光色 + 高光形状。
- 构图：史诗远景（山门、云海、巨兽）交代世界；人物中近景用浅景深把背景化开。
- 镜头节奏：大运镜（环绕、升降、跟随）比真人多，但每个运镜写叙事职责；斗法快、感悟慢。

**角色造型与比例**：风格化 3D 比例，头身比 7–8，脸精修；识别靠结构差异（下颌线、眼型、瞳孔高光形状、发型分层与渐变、不摘的配件），同剧角色逐条枚举 [套件]。环境尺度仍按现实：石阶一级约 17 cm，殿门比人高很多（写明倍数）。

**风格句**

```text
High-end Chinese 3D animated xianxia series frame, stylized but grounded 3D characters with detailed hair strands and layered silk robes, rim light on the characters, rich cinematic color grading, consistent head-to-body ratio of about 7.5, architecture and props at real-world scale, nobody looks at the camera, not flat 2D cel shading, not photographic live action, no plastic toy look, not low-poly, no text, no runes, no watermark.
```

关键词：`Chinese 3D animated xianxia`、`stylized 3D characters`、`volumetric light`、`rim light`、`drifting mist`、`spirit particles`、`layered silk robes`、`cinematic color grading`。

**视频提示词写法**：法术三拍与 §5 相同，但可以写得更大：`a ring of golden light expands outward from his palm, lifting dust and leaves in a circle, the shockwave bends the bamboo behind him toward screen-left`；御剑可以做完整飞行镜（`tracking shot following her as she flies low over the sea of clouds, her robe and hair streaming back`）；发丝与衣带是常驻动态；环绕运镜写起止角度（`the camera arcs 90 degrees from her front to her left side`）。

**声音与台词腔调**：比真人仙侠更"番剧"：旁白感、宣言式台词可以多一点（出招报名"破！"），但每集仍要有日常口语的对话；配音力度大、情绪饱满，出招喊叫必须有力度（听感验收）。

**禁忌与常见翻车**：
- 全剧角色一张脸（精修画风的头号风险）[套件]。
- 氛围光把瞳色、发色染成认不出的颜色 [套件]。
- 背景写实度与角色差档没声明，像贴纸 [套件]。
- 特效越来越大但冲突没变：力量差落在位置、持物、损伤、旁人退让的距离上 [套件 仙侠修真]。

**后端注意点**：H3 画风容易往真人漂，建议全剧走 Seedance 或先做一镜对照 [推断]；Seedance 支持更长时长（4–30 秒）和时间段写法，适合一镜完成的长斗法 [套件]。

## 8. `manhwa` 韩漫 / 条漫风

**适用题材**：复仇重生、霸总、恶女、宫廷穿书、都市异能；竖屏 9:16 优先。

**画面语言**
- 色彩：高光感的数字上色，皮肤通透、柔和渐变阴影；背景常被虚化成柔光或纯色渐变来突出人物。
- 光：柔光为主 + 强轮廓光；情绪高潮用背景爆光、花瓣、光斑（后期或模型生成均可，但不出字）。
- 构图：竖屏上下分层——上方留给脸，下方交代手和物件；大量胸像特写；条漫的"分格"感靠快切实现，不让模型画分格线。
- 镜头节奏：一镜一个情绪定格 + 轻微推近；反转那一格停得更久。

**角色造型与比例**：修长比例，头身比约 8，脸精修、下巴尖、眼睛大但不夸张；**环境尺度照样按现实**（长腿不等于能跨过桌子）。恶女、霸总的服装华丽，写清颜色和款式；识别靠发色、瞳色、配饰，同剧枚举差异。

**风格句**

```text
Korean webtoon manhwa style illustration frame, polished digital painting with clean thin line art, soft gradient shading and luminous skin, strong rim light, softly blurred glowing background, elegant slender proportions with a consistent head-to-body ratio of about 8, furniture and architecture at real-world scale, nobody looks at the camera, not Japanese cel anime, not 3D rendered, no heavy black outlines, no halftone dots, no text, no speech bubbles, no panel borders, no watermark.
```

关键词：`Korean webtoon style`、`manhwa`、`digital painting`、`soft gradient shading`、`luminous skin`、`rim light`、`glowing bokeh background`。

**视频提示词写法**：运动幅度小、质感高：发丝飘、眼神转、睫毛抖、裙摆轻晃、光斑在背景里慢慢漂；情绪爆发用"定格 + 推近 + 背景光爆开"；动作戏少，接触动作仍要双人同框。口型比日系动漫更接近真人但仍简化：`subtle mouth movement in time with speech`。

**声音与台词腔调**：台词偏戏剧化、金句化（"这一世，我不会再让你得逞"）；配音偏影视剧而非动漫声优，冷、狠、慢，关键句前停半拍。内心独白多，用 VO 后期配。

**禁忌与常见翻车**：
- 模型画出对话框、分格线、韩文字：风格句写死 `no speech bubbles, no panel borders`。
- 过度磨皮成塑料脸、所有人一张脸。
- 修长比例被放大到人比门高：写尺度锚点。
- 背景全虚化导致观众不知道人在哪：每场第一镜给一个看得清地点的中景（硬约束 6c）。

**后端注意点**：精修插画风动作大了脸容易崩，动作镜拆小 [推断]；H3 容易往真人漂 [推断]；Seedance 用 `@图片1` 锁角色设定图、写中文"韩漫风格" [推断]。竖屏项目 `aspect: 9:16`。

## 9. `cg_realistic` 写实 3D / CG

**适用题材**：科幻、末日、怪物、机甲、游戏改编、需要大量不可实拍元素但要写实质感的剧。

**画面语言**
- 色彩：电影级调色（橙青、冷灰），材质写实；每个场景写清主光源和环境光。
- 光：物理正确的光（全局光照、体积雾、金属反射），光源必须能在画面里找到或说出来（应急灯、屏幕、火光）。
- 构图：像电影镜头：前景遮挡 + 中景主体 + 远景规模感；怪物/机甲给人物作尺度参照。
- 镜头节奏：电影节奏，动作镜可更长；避免游戏过场动画式的环绕运镜滥用。

**角色造型与比例**：写实人体比例（和 `live_modern` 相同的身高锚点）；非人角色（怪物、机甲）必须写高度并给人物参照（`a mech about 6 metres tall, its knee level with the soldier's head`）。

**风格句**

```text
Photorealistic cinematic CG frame, high-end film visual effects quality, physically based materials and global illumination, realistic human proportions and real-world scale for every object, motivated light sources visible in the scene, subtle film grain and anamorphic lens character, nobody looks at the camera, not a video-game cutscene, no plastic skin, no toy-like materials, not anime, no text, no UI, no HUD, no watermark.
```

关键词：`photorealistic CG`、`film VFX quality`、`physically based rendering`、`global illumination`、`volumetric haze`、`anamorphic`、`motivated lighting`。

**视频提示词写法**：写物理后果（烟尘、碎片、火星、积水溅起、金属形变）；大物体运动写重量感（`the mech's foot lands heavily, the ground shakes and dust puffs outward`）；背景持续有东西动（警报灯旋转、火光、飘雪、远处爆炸闪光）。

**声音与台词腔调**：电影腔，克制；危机中语速快、句子短；配音情绪真实，不做动漫夸张。

**禁忌与常见翻车**：
- 塑料皮肤、游戏过场感：写 `realistic skin texture, subsurface scattering`，别写 `3d render`。
- 屏幕、HUD、仪表出乱码字：写 `no UI, no HUD`，界面信息后期加。
- 怪物、机甲大小逐镜漂移：尺度锚点写进每镜。

**后端注意点**：H3 适合人物对白镜，特效镜改写成后果镜或走 Seedance；Seedance 适合长镜头的连续动作 [推断]。

## 10. 视频后端的差异

| 项 | MiniMax H3 | Seedance 2.x |
|---|---|---|
| 提示词语言 | 英文三段骨架 | 中文自然指令 [套件] |
| 风格保持 | 真人最好；非真人是否往真人漂待本项目首批实测（§1 先各试一镜），视频头句和保持句按 §1 表换 [推断] | 需要 `@图片N` 逐项声明参考职责 [套件] |
| 特效（法术、粒子） | 偏弱，改写成"后果镜" | 时长长，适合一镜多拍 |
| 台词口型 | 原生口型最好 | 同轨生成音频 [套件] |
| 时间控制 | 会把台词拉长填满镜长，开口常晚 1–2 秒 [自测] | 整数秒时间段，仍有偏差 [套件] |
| 本 skill 写法 | [4-分镜与视频提示词.md](4-分镜与视频提示词.md) | [4-分镜与视频提示词.md](4-分镜与视频提示词.md) |

两个后端都按 [4-分镜与视频提示词.md](4-分镜与视频提示词.md) 的通则写（节拍、环境动态、表情避坑、接触同框、时序以实测为准）；以后接入别的图生视频模型也一样，只新增它的方言文件。

同一剧里混用后端时，风格句不变；如果某后端让画风漂移（例如 H3 把动漫人物拍成真人），列出受影响的镜和 2–3 个候选后端交用户定（硬约束 1b），不自己换；定了之后那一类镜头统一换，不在同一场里混。

## 11. 风格审查问题

reviewer 看视觉设定和分镜时的风格必答问题统一在 [6-审片与剪辑.md](6-审片与剪辑.md)：画风匹配见 §A-8，台词腔调与术语解释见 §D-9，头身比与尺度见 §D-5，风格句、常见翻车、法术三拍、视频头句、漂移诱因词、系统面板、制作形态卡与叙事职责见 §E5（第 1–9 条）。写作者按本文件 §1–§10、§13 写完后可用同一清单自查。

## 12. 系统面板主题预设（后期叠加的弹窗、面板、卷轴）

金手指面板、系统提示、灵识感应、圣旨这类"画面上的字"全部走 cut.py 的 `panel` 叠加（生成画面里不出字）。用户原话："系统弹窗做的有科技感一点。"面板样式按画风选主题，写进 `drama.json` 的 `overlays.panel`，全剧一种主题（与 `style_preset` 一样锁定）；单条面板要换标题时在 overlay 里写 `title`。字段和默认值见 edit-and-delivery §4，预览用 `cut.py --panel-demo`。

| 主题 | 适用画风 | 外观 | 入场与声音 |
|---|---|---|---|
| `tech` 都市科技（默认） | `live_modern`、`cg_realistic`、现代题材的 `anime_cel` / `manhwa` | 半透明深色玻璃底（毛玻璃模糊背景）、冷青细描边 + 外发光、电蓝 HUD 角标、六边形图标 + 等宽英文标题 `SYSTEM`、细扫描线、轻微全息抖动 | 0.32 秒缩放入场、光带扫过、逐字打出带光标；电子"叮" |
| `xianxia` 修仙灵光符文 | `live_xianxia`、`guoman_3d`、修仙题材的 `anime_cel` | 深褐半透明玻璃底、金色描边 + 金光外发光、玉青色符文环图标、宋体/明朝体标题（默认「灵识」）、无扫描线、不抖动 | 缩放入场、金色光带扫过、逐字较慢（每秒 14 字）；钟磬声 |
| `scroll` 古风卷轴 | `live_period`、宫廷与古装 | 宣纸色不透明底、深褐细边、左右两根卷轴、朱红方印图标、宋体正文、无外发光、无玻璃 | 0.4 秒从中间向两边横向展开、逐字像落墨（每秒 10 字）；纸声 |

写法：

```jsonc
// 真人都市：默认 tech，只改主色和标题
"overlays": {"panel": {"theme": "tech", "accent": [0, 229, 255], "title": "SYSTEM", "position": "top_left"}}
// 修仙：灵识提示
"overlays": {"panel": {"theme": "xianxia", "title": "灵识", "position": "top"}}
// 宫廷：圣旨、诏令
"overlays": {"panel": {"theme": "scroll", "position": "center", "width": 0.42}}
```

- 主色不要和同场的印章字（`overlays.stamp.color`）撞色；`tech` 常用冷青 / 电蓝 / 警示橙（`[255, 150, 40]`，用于"危险""倒计时"一类面板），`xianxia` 按角色法术颜色选，但全剧一套。
- 面板位置默认左上，避开右上角前 3 秒的 AI 标识和说话人的脸；起始帧构图给面板那一侧留空（和印章字留空同一个道理）。
- 面板文字短：一行一件事，最多 3 行；数字、次数、倒计时写成面板，规则解释写成台词（story-engine §7）。

## 13. 制作形态卡：每种画风额外要写的字段

`style_preset` 和 `style` 决定风格句；形态卡决定**哪些字段必须展开、哪些可以省、运动的默认值是什么**。形态不改提示词的段序（storyboard-keyframes §6 的顺序不变），改的是每一段写什么。判断一条形态描述有没有内容，只问一句：删掉它，提示词会不会变；不变就只是标签，删掉。

形态卡是手艺默认：导演岗可以在决策记录写理由覆盖，形态卡本身不产生新的机械门；头身比、rig 姿势边界这类本项目制作约束，写进视觉设定才对本项目生效。与本 skill 硬约束（画面不出字、比例真实、台词多、能力说出来、环境运动按需）冲突时，以硬约束为准，下文已按硬约束改写。

### 13.1 preset 对应哪张形态卡

| preset | 形态卡 | 这种形态最先决定的事 | 最容易丢的东西 |
|---|---|---|---|
| `live_modern` / `live_period` / `live_xianxia` | 实拍 | 可搭建的空间、真实光源、可表演的动作、现场声源 | 造型状态的逐镜可比较性（袖口、湿污、伤妆） |
| `anime_cel` | 二维动态漫 | 形状语言、色块与阴影分区、每镜哪一层会动 | 剪影级身份锚点 |
| `manhwa` | 精修单帧（国漫二次元规则）+ 二维的可动层写法 | 角色之间可枚举的结构差异、氛围色边界 | 人物之间的区分度 |
| `guoman_3d` | 风格化三维 + 精修单帧的结构差异 | 比例、接触、摄影机空间；角色差异枚举 | 接触点与重量结果、人物区分度 |
| `cg_realistic` | 风格化三维（写实材质） | 比例、接触点、重量与物理后果 | 接触点与重量结果 |
| （无）水墨笔触、Q 版 | 见 §13.4 | | |

**身份锚点载体随形态变**：实拍写可比较的造型状态（袖挽到哪一截、扣到第几颗、左眉旧疤），不写长相评价；二维写剪影、色块和一两个图形记号（领口形状、发饰），自检用"剪影测试"——把人物填成纯黑还认不认得出；三维写头身比、肩宽、材质分区和 rig 做不到的姿势；精修类（`manhwa`、`guoman_3d`、日漫精修）五官被修得很像，只能靠**逐条枚举的结构差异**：下颌线、眼型与瞳孔高光形状、发型分层与渐变位置、一件不摘的配件，枚举到同组角色能两两分开为止（写"清冷美人"不算锚点）。

### 13.2 连续性：逐镜必带什么、可以省什么

| 形态 | 逐镜必带 | 通常可省 | 最常断的地方 |
|---|---|---|---|
| 实拍 | 造型层次与整洁度、湿污伤的程度与位置、手中物、光源时段与方向、妆发随时间的衰减 | 不出画的内层、观众无从比较的陈设 | 袖口衣褶、食物烟酒的消耗量、伤妆进展方向 |
| 二维动态漫 | 轮廓与色块、阴影分区（阴影落在哪块）、描边粗细与有无、本镜可动层清单 | 写实材质、精确布光角度、背景纵深 | 阴影分区换逻辑、描边时有时无、配色饱和度漂移 |
| 风格化三维 | 比例剪影、材质分区与粗糙度、接触点（脚踩哪个面、手握物体哪一段）、光向与体积介质、轴线与机位高度 | 次要形变、看不见的背面 | 脚离地或穿模、持物无来源换手、同场光向或轴线翻转 |
| 精修单帧 | 脸眼发结构、瞳色与高光形状、发色渐变、固定配件、当前氛围色与光源色温、脸上高光阴影的落位 | 背景纵深、不承重的装饰 | 氛围光把瞳色发色染到认不出、高光形状逐镜变、全剧人物趋同 |
| 水墨笔触 | 不可洇化的轮廓与墨记号、本场浓淡层级、手中物、必要地理、留白方位 | 精确光向、纹理细节 | 人物被洇化吃掉、手中物在留白里消失、浓淡层级前后颠倒 |
| Q 版 | 头身比与角色间相对尺度、主色块、放大记号、手中物、后期叠字的预留位 | 写实材质、背景细节 | 角色间尺度逐镜变、道具时大时小、放大记号在某些角度消失 |

这些必带项写进视觉设定的锚点和锁（visual-assets §6），起始帧和视频提示词只带本镜会变或可能漂的那几项，不把不变层每镜重复一遍。

### 13.3 分层与运动默认值

每种形态都按四层想：**身份层**（人物与造型，跨镜锁定）、**环境层**（底板、空间几何、可走的路径）、**可动层**（本镜真正会动的部分）、**效果层**（光斑、粒子、烟、法术光、景深）。每镜只写发生变化的层；效果层不得盖掉身份层的识别色和不可洇化的边缘。

- **实拍**：默认全动作，要写的是限制——同一镜并行几件事、道具交接换几次手、台词在动作前还是后。因果转折、证据交接、被看见的选择必须在镜内完成；长距离位移、换装、时间跨度交给剪辑。不要把心理状态默认翻译成发抖、冷汗、瞳孔放大这类症状，写人物正在处理的对象和选择（video-prompts-general §5 的表情写法）。
- **二维动态漫**：默认 limited motion，静止是主动的注意力选择，不算失败。每镜点名：哪层 hold、哪层局部循环（呼吸、发梢、衣摆）、哪层做视差、哪里用一次姿势切换代替连续动作；冲击可以用效果层加顿帧承接。不给所有人物、头发、衣摆和背景同时加没有原因的运动——那是这个形态最典型的廉价感来源，和"环境运动按需"（§2 第 3 条）一致。
- **风格化三维 / 写实 CG**：默认可以全动作，但摄影机是最贵的一层，运镜要写动机（跟随、揭示、施压），不为展示空间做连续环绕。必须全动作的是承担因果的接触事件（递交、抓握、推倒、落地），写落脚下沉、被压出的形变、碰撞后的余势，不写"流畅自然"。**接触即有声**：落地、放置、碰撞、摩擦都要落成 `sfx`（edit-and-delivery §5），缺了重量感就垮。
- **精修单帧（韩漫、国漫、日漫精修）**：全动作预算集中给情绪转折镜（眼神变化、转身、伸手），对白镜用口型、眨眼、发梢循环和极轻的呼吸位移撑住；缓推要写叙事职责，否则每镜都会默认缓推。背景写实度比人物低一档时要在视觉设定里声明，否则人物像贴纸。
- **口型策略**立项时定下并全剧一致（不做口型 / 简化开合 / 接近完整口型），它决定台词怎么写：不做口型的画风里，长台词让说话人背身或侧身，但仍要拍说话人在镜的镜头或用 `audio_from` 垫音（H3 不生成画外人声，硬约束 11）；不能因为口型难做就砍台词量（台词多、反应快的预设不变）。

### 13.4 预设之外的两种形态：水墨笔触、Q 版

G33 只认七个 preset 值。做水墨或 Q 版时，`style_preset` 借最近的一个（水墨、Q 版都借 `anime_cel`），`style` 和视频保持句整句换成下面的写法，决策记录写一行"style_preset 借用 anime_cel，实际形态为水墨笔触/Q 版，原因……"。视频头句沿用 `anime_cel` 那一行。要正式新增 preset 值，需要同时改 `shots_tool.py` 的 G33 和 `project_tool.py init --style-preset` 的可选值，目前没做。

**水墨笔触**：用浓淡决定观众先看到什么，用留白决定什么暂时不让知道；擅长关系压力、动作余势和心理距离，不擅长精确地理、机械结构和可读细节，这些要另找载体保住。

| 墨的一项 | 承担什么 |
|---|---|
| 浓淡 | 注意力顺序（本场谁最浓） |
| 干湿 | 时间与用力程度 |
| 飞白 | 速度与撕裂 |
| 洇化 | 情绪扩散或时间流逝 |
| 留白 | 未知、距离、被拒绝的信息（留白是设计过的未知，要能说出何时释放，配合 scene-state-and-reveal 的观众认知账） |
| 笔势 | 动作方向与余势 |

- 视觉设定必须点名**哪些边缘绝不洇化**：人物身份轮廓、手中物、必要地理（门、桌、水岸）。没有这一条，每一次"加点水墨感"都会合法地把人物吃掉一点。
- 着彩只给一个焦点，多一处就和浓淡抢注意力。
- 运动预算极低：大部分 hold，只让少数墨迹动（洇开的一小块、飘散的笔触、从留白里进入的一笔）；转折靠墨的状态变化，不靠人物全动作。不给所有笔触加持续抖动。
- 题款、竖排字、印章一律不让模型画，后期叠加（硬约束 4）。
- 风格句参考：`Chinese ink-wash animation frame, expressive brush outlines with dry-brush streaks, layered ink tones from pale grey wash to dense black, generous unpainted paper space, one restrained colour accent at most, the character outline, hands and held objects stay crisp and never bleed, furniture and architecture at real-world scale, nobody looks at the camera, not photographic, not 3D rendered, no calligraphy, no seals, no text, no watermark.` 视频保持句参考：`The whole take stays an ink-wash frame: only the named ink strokes move, the character outline never dissolves, the paper texture stays constant.` [推断：未在 H3 实测，先按 §1 各试一镜]

**Q 版表达**：用夸张比例降低威胁感和认知负担，让情绪一眼可读、因果只剩必要元素；擅长规则、流程、风险和让沉重题材被接受，不擅长细节写实和严肃的暴力后果。

- 每个角色的头身比选定后跨镜不变（不同角色可以不同）；识别靠发型剪影、主色块和一处刻意放大的记号（眼镜、呆毛、工牌），五官细节不做锚点。
- **只改头身比，不改环境尺度**（§2 第 1 条）：护栏仍到腰、门仍比人高。
- 一个镜头只承载一个因果单位；默认 hold 加局部动，动的只是执行因果的那只手或那个物体。可爱不等于持续弹跳，全员弹跳会让因果读不出来。
- 问号、汗滴、箭头、高亮圈这类符号层一律后期叠加或做成无字图形，而且**不能替代事实本身**：箭头指着不等于已经展示了后果，后果仍要有画面。
- 规则由角色台词或字幕明说（能力说出来的硬约束），画面负责证据和后果；不靠旁白代替角色开口。
- 危险动作、错误示范能不能完整演示，立项时定在系列简报里，不在提示词阶段临时判断。
- 风格句参考：`Chibi-style 2D animation frame, super-deformed characters with a fixed head-to-body ratio of about 2.5, bold clean outlines, flat saturated colour blocks with one soft shadow tone, simple background that keeps only the objects the action needs, furniture and doors at real-world scale relative to the characters, nobody looks at the camera, not 3D rendered, not photographic, no text, no symbols, no speech bubbles, no watermark.` [推断]

### 13.5 混合形态与异质身体

- **混合形态**（三维人物配绘制背景、真人配笔触后期等）不新建一种形态，取两张卡，逐项写清谁负责身份、深度、边缘、光和运动；同一个事实由两层同时决定是最贵的错误（边缘抖、光打架、改一处要改两处）。混合组合本身在立项时锁定，全剧不变（§1 全剧锁定一种）。
- **异质身体与特殊介质**（身份互换、变形、水下、失重、微缩、非人角色）：先在视觉设定该人物条目下写一张物理卡，分镜和视频提示词只投影，不临时发明身体规则：
  - 身体拓扑：现在有哪些肢体或形态、明确没有什么、接触和发力点在哪；
  - 身份占用：谁的意识占用哪个身体，别人此刻怎么认出他，什么时候允许变化；
  - 环境介质：水流、浮力、重力、风怎样改变静止、移动、衣服毛发和道具；
  - 运动语法：为这个身体选悬浮、摆尾、攀附、滑行这类动作词，删掉和物理冲突的陆地动作词；
  - 连续性硬项：形态、呼吸或受力状态、持物方式逐镜继承；
  - 软呈现项：冷暖、笔触、景深、光效可以变，但不能冲掉上面的硬项。
  普通人物只是换衣服或情绪变化时不建这张卡。

### 13.6 各阶段多写的那一件事

| 阶段 | 所有形态都要做 | 按形态多写 |
|---|---|---|
| A 立项 | 选 preset、锁风格句与视频头句（§1）、必要时做 §1b 试镜 | 口型策略、运动预算给哪类镜、混合层分工、水墨着彩与留白策略、Q 版安全边界 |
| D 视觉设定 | 锚点、锁、尺度（visual-assets） | 实拍的造型状态版本；二维的色块与阴影分区；三维的比例与 rig 边界；精修类的角色差异清单与背景差档；水墨的不可洇化边缘；Q 版的头身比与放大记号；异质身体的物理卡 |
| E 分镜与提示词 | 职责、起止、接触同框（storyboard-keyframes） | 二维与精修：本镜可动层；三维：接触点、重量结果、运镜动机；水墨：会动的墨迹及其职责；Q 版：这一镜唯一的因果单位 |
| 审查 | review-checklists §E5 第 1–8 问 | §E5 第 9 问及 §13 各形态自检 |

## 来源（2026-09-25 调研补充）

新增条目的行尾标注：[官方] 厂商官方文档；[社区] 社区教程、平台博客或开源项目；[自测] 本项目实测或复盘；[推断] 未实测的推论。风格句、视频保持句和色调句都是按来源原则自己改写的，没有照搬。

- H3 官方示例（fal 托管，风格写成"要保留的质感 + 拒绝项"、远景用背影）：https://fal.ai/learn/devs/minimax-h3-prompting-guide
- H3 官方提示词拆解（不写拒绝项会自加字幕、转场）：https://www.atlascloud.ai/blog/tips/minimax-h3-prompt-guide
- MiniMax Hailuo 2.3 发布说明（风格化稳定性增强）：https://www.minimax.io/news/minimax-hailuo-23
- 动漫风漂移诱因词与恒定线宽：https://www.atlascloud.ai/blog/tips/seedance-2.5-anime-prompts-style-control
- 风格前缀同时注入图片与视频、邻近画风排除（CC BY-NC-SA，只借结构）：https://github.com/kongxg888/huobao-drama
- 打斗与法术的受力写法：https://news.qq.com/rain/a/20260329A01Y0300
- 仙侠稳定镜头类型：https://morphic.com/resources/videos/xianxia-videos
- 光的可执行词汇：https://deepmind.google/models/veo/prompt-guide/
