# 生产通道：各模型的参数、限制与收回规则

阶段 F–H 要把参考图、起始帧、视频、配音或配乐送到某个具体模型时读本文件。默认通道是 H3 自建中转（`h3_client.py` / `produce.py`，见 [production-and-review.md](production-and-review.md) §1–2）；用户把某一类生成指定给官方接口时走 `scripts/providers.py`。**用哪个通道、哪个模型、哪个档位和分辨率由用户指定**（SKILL.md 硬约束 1b）：本文件只说明用户定了之后参数怎么填、哪些组合会被拒绝，以及交用户挑选时列候选的依据；不据此自选或换模型。

## 目录

0. 所有通道共同的纪律
1. 接一个新模型前要写清的能力
2. MiniMax 视频（H3 官方接口）
3. Seedance 2.0 / 2.5
4. MiniMax 语音
5. MiniMax 配乐
6. GPT Image 2
7. 失败怎么分、结果怎么收回
7b. fal 队列通道
8. `providers.py` 用法

## 0. 所有通道共同的纪律

- **密钥只从环境变量读**：`H3_STUDIO_TOKEN`、`FAL_KEY`、`MINIMAX_API_KEY`、`ARK_API_KEY`、`OPENAI_API_KEY`。不写进 `drama.json`、job 文件、账本、日志、提交或回复；job 的 `parameters` 里出现 key/token 字样直接拒绝。
- **串行与账本**：`providers.py` 复用 `h3_client.py` 的账本 `脚本/jobs.jsonl`、提交锁和 STOP/DEADLINE。提交前先查未决提交和同名未收回任务；先写 `submission_intent` 再 POST；拿到任务号立即写 `submitted`，早于第一次轮询；POST 永不自动重发，只重试 GET（runtime-boundaries.md）。
- **全参数显式**：模型 ID、时长、分辨率、比例、语言每次都在 job 里写出来，不靠服务端默认。视频模型的可用时长区间和分辨率集合按账号实际开通的型号写环境变量（§2、§3），不写死在脚本里——不同版本的范围不一样。
- **本地参考直接内联**：项目里的参考图、参考视频、参考音频按 `data:<mime>;base64,…` 送出（两家官方都接受），不需要自建上传服务。送出前校验文件头与扩展名一致；单文件上限图片 30MB、视频 50MB、音频 15MB，整请求 base64 后 64MB（MiniMax 公布值，Seedance 未公布，沿用同一保守上限）；超了就把大文件放到 HTTPS 地址再绑定，不拆文件。
- **参考约束随提示词一起送**：每张参考在 job 里写 `label`（中文名）、`role`（供应商素材角色）、`may_control`（这张图管什么）、`must_not_control`（不管什么）；`providers.py` 按送出顺序把它们追加在正文后面，编号用该模型自己的记号（H3 `<Picture N>`，Seedance `@图片N`），语言跟正文一致。只上传文件、丢掉职责说明是错的。
- **成功不等于质量**：接口返回成功、文件存在、哈希一致，只说明任务执行了；像不像、演得对不对、口型和声音对不对，仍按 production-and-review §4–5、§10 看图听审。
- **不删产物**：输出路径已存在就拒绝，重拍开新 take。

## 1. 接一个新模型前要写清的能力

换模型或第一次接某个模型时，把下面十条写进 `项目开发/决策记录.md`（用户给的说明或官方文档，标来源），没写清的按"未声明"处理，不从模型名字猜：

| 能力 | 要写什么 | 影响什么 |
|---|---|---|
| 模型版本 | 账号里的 Endpoint / 模型 ID | 只按这个版本的方言写（video-prompts-general 开头的方言路由） |
| 提示词方言 | 通用自然语言，还是有原生结构（H3 三段/六段、Seedance 素材标记） | 正文结构 |
| 单次时长 | 最短、最长秒数，是否支持自动时长 | `shot_seconds` 能否落在范围内；长镜头上限 |
| 参考方式 | 无 / 首帧 / 首尾帧 / 多槽参考及上限；首尾帧与参考是否互斥 | 起始帧和身份图怎么一起送 |
| 声音 | 与画面同一次生成，还是只出画面 | 同轨要写完整声音时间线（video-prompts-general §9）；不同轨只写后期职责 |
| 画幅与分辨率 | 实际接受的集合 | `aspect`、`profiles.*_res` |
| 正文长度上限 | 字符数 | 超限先删起始帧已承载的重复描述；锁面、逐字台词不删 |
| 运镜词 | 是否接受具名运镜术语、有没有官方词表 | 不接受就写画面关系变化 |
| 正文语言 | 这个模型本次用什么语言写正文 | `prompt_lang`；台词仍是剧本原语言 |
| 负面提示通道 | 无 / 独立字段只收名词 / 官方中文默认词 | video-prompts-general §11 |

模型说明里"效果较好""稳定性下降"一类措辞标出的是不稳定区，写作时就收窄（video-prompts-general §11）。

## 2. MiniMax 视频（H3 官方接口）

走官方 `POST {base}/video_generation` 创建异步任务，`GET {base}/query/video_generation/{task_id}` 轮询，成功后下载 `task.content.url`。和自建中转是两条不同的路：中转的档位名（例如 `base50_sol`）不是官方模型 ID，不能混填。

| 环境变量 | 说明 |
|---|---|
| `MINIMAX_API_KEY` | 必填 |
| `MINIMAX_VIDEO_RESOLUTIONS` | 必填，账号型号实际接受的分辨率，取自 `480P`、`768P`、`2K`，逗号分隔 |
| `MINIMAX_VIDEO_MIN_DURATION` / `MINIMAX_VIDEO_MAX_DURATION` | 必填，整数秒区间（H3 官方为 4–15；`MiniMax-H3-Max` 是另一型号：5–15 秒、`480P`/`768P`、不支持 full-reference） |
| `MINIMAX_VIDEO_RATIOS` | 可选，限定可用比例（`adaptive`、`1:1`、`3:4`、`4:3`、`9:16`、`16:9`、`21:9`） |
| `MINIMAX_VIDEO_BASE_URL` | 可选，默认 `https://api.minimax.io/v2`，必须是 https |

job 的 `model` 写用户指定的模型 ID（脚本没有默认值）。`parameters`：`duration`（整数秒，必填，只能在上面区间内；正文里写秒数不能代替它）、`resolution`（必填）、`ratio`（文生视频必填且不能是 `adaptive`，有参考图时可省）、`prompt_language`（正文语言，只用于追加参考约束，不作为请求字段送出）。

- 正文进 `content` 的第一个 text 项，加上参考约束后不能超过 7000 字符。
- 参考素材逐个进 `content`，`role` 取 `first_frame`、`last_frame`、`reference_image`、`reference_video`、`reference_audio`；首帧、尾帧各最多一张；参考图最多 9、参考视频最多 3、参考音频最多 3，视频和音频每段 2–15 秒、各自合计 ≤ 15 秒（脚本查个数，时长由写 job 的人按 ffprobe 核对）。
- **首尾帧与参考输入互斥**：起始帧加身份图/底板时整组走 `reference_image`，正文用六段 full-reference（video-prompts-h3 §11）。续接上一段实际结果时，上一段视频走 `reference_video`、它的实际尾帧走 `reference_image`，不把尾帧标成 `first_frame`。
- 参考音频必须配至少一张参考图或一段参考视频。
- 官方视频接口没有单独的语速参数；台词装不装得下按 video-prompts-h3 §3 的发声窗口算，放不下回分镜加秒数。

## 3. Seedance 2.0 / 2.5

走火山方舟 `POST {base}/contents/generations/tasks` 创建异步任务，`GET {base}/contents/generations/tasks/{id}` 轮询，成功后下载 `content.video_url`。正文写法见 [video-prompts-seedance.md](video-prompts-seedance.md)。

| 环境变量 | 说明 |
|---|---|
| `ARK_API_KEY` | 必填 |
| `SEEDANCE_MIN_DURATION` / `SEEDANCE_MAX_DURATION` | 必填，整数秒区间：2.0 为 4–15，2.5 为 4–30 |
| `SEEDANCE_ALLOWED_RATIOS` | 可选，限定可用比例 |
| `SEEDANCE_BASE_URL` | 可选，默认 `https://ark.cn-beijing.volces.com/api/v3` |

job 的 `model` 写用户开通的 Endpoint/模型 ID，脚本不假设是 2.0 还是 2.5。`parameters`：`duration`（正整数或 `-1`；本流程固定镜长，不用 -1，edit 除外）、`ratio`、`generate_audio`（布尔）、`omni_reference_task_type`（2.5 的 `reference` / `edit` / `extend`）、`prompt_language`。

- `role` 取 `first_frame`、`last_frame`、`reference_image`、`reference_video`、`reference_audio`；首帧、尾帧各最多一张，各占一个 `@图片N` 序号。首尾帧能否与其他参考混用按接口实测，H3 的互斥规则不套过来。
- `edit` 必须 `ratio: adaptive`、`duration: -1`、有参考视频；`extend` 必须 `ratio: adaptive`、有参考视频。任务类型和正文语义不一致时 2.5 会拒绝；类型是创作决定，脚本不从关键词猜。
- 返回的 `duration` 是按帧数向下取整的近似值，实际时长用 `ffprobe` 量。

## 4. MiniMax 语音

`POST {base}/t2a_v2`，非流式、`output_format: hex`，结果随响应返回（同步通道，账本记 `sync-<request_id>`）。环境变量 `MINIMAX_API_KEY`，可选 `MINIMAX_BASE_URL`（默认 `https://api.minimax.io/v1`）。

- job 的 `prompt` 就是要念的那一句：剧本原句，加上按 `emotion` 插入的语气词和停顿标注，不改字（production-and-review §10）。一句一个 job、一个情绪；中途变情绪的句子拆两段生成再拼。
- `model` 必填（用户指定的 speech 型号），`parameters.voice_id` 必填：音色写在 refs.json 该角色的 `voice` 和视觉设定里，由用户确认；脚本只查格式，不内置音色清单——哪些预置音色可用取决于型号和账号，以供应商音色列表为准。本通道只用预置音色合成，不做声音克隆；克隆涉及声音授权，走用户提供并授权的参考录音和其他引擎。
- `language_boost` **必填**，写台词语言（`Japanese`、`Chinese`、`Chinese,Yue`、`English`、`Korean` 等），不收 `auto`：汉字多的日语句被自动判成中文，就会带中文口音和声调。音色本身也要是该语言的母语音色，音色的语言写在 `voice` 旁边。
- `emotion` 只收 `happy`、`sad`、`angry`、`fearful`、`disgusted`、`surprised`；平读不传 emotion。官方 2026-09-25 的列表另有 `calm`、`fluent`、`whisper`（后两个只在 speech-2.6，2.8 不收 `whisper`），`neutral` 已不再列出；这些未经本项目实测，脚本不收。
- `speed` 0.5–2.0、`vol` 0.1–10、`pitch` -12–12 整数；`sample_rate` 16000/24000/32000/44100，`bitrate` 32000/64000/128000/256000；`format` 为 mp3 或 wav 且与输出扩展名一致。
- `pronunciation`：`{"売上": "うりあげ", "夏樹": "なつき"}`，脚本转成官方 `pronunciation_dict.tone`（`原词/读法`，读法可以是假名、带声调数字的拼音 `(chong2)` 或 IPA），原词必须出现在这句里。来源是 `drama.json` 的 `readings` 和 `dialogue[].reading`，提交前逐条核对。
- 语气词（只有 speech-2.8-hd / 2.8-turbo 支持）：`(gasps)`、`(pant)`、`(sighs)`、`(sniffs)`、`(breath)`、`(inhale)`、`(exhale)`、`(laughs)`、`(chuckle)`、`(groans)`、`(emm)`；停顿 `<#x#>`（x 为 0.01–99.99 秒，放在两段可念文本之间，不连用两个）。做字幕和 ASR 比对前剥掉所有 `(…)` 与 `<#…#>`，字幕以剧本原句为准。

## 5. MiniMax 配乐

`POST {base}/music_generation`，模型固定 `music-3.0`，非流式 hex 返回（同步通道）。配乐属于剪辑层（edit-and-delivery）：生成的是源音轨，落点、循环、淡入淡出和对白 ducking 仍在剪辑时做。

- 配乐任务之前先在 `剪辑单.md` 或决策记录写清这段音乐：用在成片哪一段（起止秒）、承担什么剧情作用（画面和表演为什么不够）、从哪里进、到哪里出、是否压在对白下。音乐任务不塞进每个镜头的视频生成里。
- `prompt` 只写音乐本身：风格、情绪、配器、能量走向，例如 `Instrumental restrained urban drama score, low pulse, sparse piano, muted strings, controlled tension, no triumphant release.` 不写模型名、艺人名或"模仿某曲"。
- `parameters.is_instrumental: true` 是纯配乐，不带歌词；带人声的歌必须给 `lyrics`，歌词来自用户提供或确认的原文。`lyrics_optimizer` 一律不开：供应商改写的歌词没有经过用户确认。
- `format` 为 mp3 或 wav 且与输出扩展名一致；`sample_rate`、`bitrate` 取值同 §4。供应商不保证精确时长，拿到后按实际长度剪。

## 6. GPT Image 2

无参考图走 `POST {base}/images/generations`（JSON），有 1–16 张参考图走 `POST {base}/images/edits`（multipart `image[]`）。模型固定 `gpt-image-2`、每次一张、结果为 `b64_json`（同步通道）。环境变量 `OPENAI_API_KEY`，可选 `OPENAI_BASE_URL`（https）。

- 尺寸用 `size: "宽x高"` 或 `width` + `height`：边长能被 16 整除、宽高比在 1:3 到 3:1、边长 ≤ 3840、总像素 65.5 万–829 万；也可 `auto`。
- `background` 只收 `auto` / `opaque`（不支持透明）；`quality` 取 `auto` / `low` / `medium` / `high`；`moderation` 取 `auto` / `low`。输出扩展名决定 png / jpeg / webp。
- 参考图走高保真编辑，不再传旧的 `input_fidelity` 字段。参考图的分工句照 visual-assets §7–8 写进正文，`providers.py` 另追加一段参考约束。

## 7. 失败怎么分、结果怎么收回

| 情况 | 账本 | 下一步 |
|---|---|---|
| POST 收到明确拒绝（HTTP 4xx、`base_resp.status_code` 非 0） | `not_submitted`，附 HTTP 状态 | 没受理不计费。429 等一会儿在授权次数内重投；其他 4xx 先看是哪一项输入被拒，只改那一项 |
| POST 网络断开、超时、HTTP 5xx（可能是网关超时而后端已受理）、响应不是 JSON、响应里没有任务号 | `submission_unknown` | 可能已计费。到供应商任务记录里找，按 runtime-boundaries.md `reconcile`；找到任务号就 `collect`，禁止直接重投 |
| 已拿到任务号，轮询或下载中断 | `submitted`（或 `download_failed`） | `providers.py collect` 按任务号收回，不走任何重新提交 |
| 任务终态失败（failed / cancelled / expired） | `failed` | 按 production-and-review §7 诊断；技术失败有上限原样重投，内容缺陷改提示词 |
| 返回未知状态、轮询超时 | 不变 | 稍后再 `collect`，不重投 |
| 下载内容和扩展名对不上 | `download_failed` | 再 `collect`；仍不对就查结果地址，不当作生成失败重拍 |

- **被拒的是哪一项就只改那一项**：提示词被拒改写那一句（"一拳砸在对方脸上，血顺着下巴滴"改成"一拳挥空，对方侧身避开，桌上的杯子被带倒"）；参考图被拒换一张构图和角色一致、画面本身合规的图；音频被拒重做那一句。改了什么写进决策记录；原样重投被拒的内容只会再花一次钱。
- **同一内容重复提交是成本信号**：账本里同一 `fingerprint` 出现第三次以上时先停下诊断（production-and-review §6–7），不当作"随机性"继续投；它本身不证明重投合理或不合理。
- **已收回文件被改动**：`视频/`、`起始帧/` 里的文件大小或内容和收回时不一致（被覆盖、被剪辑工具就地改写），先确认手上用的是哪一版，再决定是否重出，不拿不明来源的文件进审片。

## 7b. fal 队列通道（MiniMax H3 Max / H3 Max Turbo，2026-09-26 实测接通）

用户指定用 fal 时：`drama.json` 写 `"video_provider": "fal"`，`profiles.video` 写 fal 端点 ID（例 `minimax/h3-max-turbo/image-to-video`），`profiles.video_res` 写 `480P`/`768P`/`1080P`；密钥只放环境变量 `FAL_KEY`（不写文件、不写回复）。`produce.py videos` 自动走 `scripts/fal_client.py`；起始帧、参考图仍走 H3 中转。

- **时长只收整数 5–15 秒**：镜头秒数向上取整、不足 5 取 5（本地 H3 的 4 秒镜会变 5 秒，剪辑按取用区间收）。
- **`prompt_expansion_mode` 固定 `disabled`**：默认 `balanced` 会改写提示词，逐字台词会被改。
- **可以并行**：fal 是云端队列，`produce.py videos … --jobs 16` 每镜一个线程；提交仍经账本锁逐条记 intent→submitted，等待与下载并行。本地 H3 单卡**不许**用 `--jobs`（脚本会拒绝）。实测 29 条 768P 5 秒视频 81 秒出齐，约 0.02 美元/秒。
- 起始帧 data URI 内联；结果从 `video.url` 的 CDN 地址下载（不带密钥）；中断用 `fal_client.py collect --root <项目> --job <request_id> --endpoint <端点> --out <路径>` 收回。
- **起始帧也可走 fal**：`drama.json` 写 `"frame_provider": "fal"`、`profiles.frame` 写图片编辑端点（例 `alibaba/qwen-image-3/edit`，1K 约 0.04 美元/张）；最多 3 张参考图（按 `frame_refs` 顺序 = image 1/2/3，提示词里的 Picture N 自动改成 image N），`enable_prompt_expansion` 固定关；`produce.py frames … --jobs 16` 并行。参考图（身份图、底板）仍走 H3 中转。
- 画质与本地 H3 同源、风格稳定；同样有约 0.5–2 秒的镜内切景和状态细节丢失，审片照 production-and-review 的 E1–E12 处理。

## 7c. 可灵开放平台（kling-v3，2026-09-26 实测接通）

用户指定可灵时：`drama.json` 写 `"video_provider": "kling"`，`profiles.video` 写模型名（例 `kling-v3`），`profiles.video_res` 写 `std`（720p）或 `pro`（1080p）；密钥只放环境变量 `KLING_API_KEY`（`Authorization: Bearer`），域名 `KLING_API_BASE` 默认北京站 `https://api-beijing.klingai.com`（新加坡站同一 key 报 `api key not found`）。`produce.py videos` 自动走 `scripts/kling_client.py`。

- **型号要按账户实测**：模型名合法但资源包没开通时返回 `model is not supported`（例 `kling-3.0-turbo`），不要猜着换型号，报给用户选。`GET /account/costs?start_time=&end_time=`（毫秒）查资源包余额与并发。
- **时长整数 3–15 秒**：镜头秒数向上取整、不足 3 取 3。
- **原生音频逐镜开关**：请求字段 `sound` on/off。镜头写 `kling_sound` 就用它；没写时有在镜台词（`dialogue[]` 里不含 `"vo": true` 的项）开，否则关；心声、画外声标 `vo: true` 后期另配。
- **起始帧**：原始 base64（不带 `data:` 前缀）放 `image`；结果从 `data.task_result.videos[0].url` 下载。
- **并发**：试用包 5 并发，`produce.py videos … --jobs 5`。
- **探测参数的坑**：1×1 像素图不会被同步拒绝，会建成任务再终态失败；只用会被同步校验拒绝的错误值（错误的 `mode`、`duration`、`sound` 会同步返回允许值列表）。
- 中断收回：`kling_client.py collect --root <项目> --job <task_id> --out <路径>`。

参考图也可走 fal：`"ref_provider": "fal"`，`profiles.ref` 写文生图端点（例 `alibaba/qwen-image-3/text-to-image`），有 `refs` 的派生底板自动改走 `profiles.frame` 的编辑端点。

## 8. `providers.py` 用法

```bash
S=<drama-forge>/scripts
python3 $S/providers.py compile --job 脚本/jobs/V_EP001-S03_t2.json --root <项目>   # 只编译，打印请求体（参考数据省略），不联网
python3 $S/providers.py run     --job 脚本/jobs/V_EP001-S03_t2.json --root <项目>   # 提交或收回同名未收回任务，下载
python3 $S/providers.py collect --provider minimax-video --task <任务号> --out 视频/V_S03_t2.mp4 --root <项目>
python3 $S/h3_client.py --root <项目> unresolved                                   # 未决提交与中转共用同一本账
```

job 文件（路径相对项目根；`name` 沿用 produce.py 的命名：视频 `V_<镜>_t<take>`、起始帧 `F_<镜>_t<take>`、参考图用图 ID，配音 `A_<镜>_<句序>_t<take>`；账本按它找同名未收回任务，和中转任务同名就会互相挡住，这是有意的）：

```json
{
  "name": "V_EP001-S03_t2",
  "provider": "minimax-video",
  "model": "<用户指定的模型 ID>",
  "prompt": "integrated_multimodal_description: [Shot 1] …\noverall_soundscape: …\nnon_diegetic_music: N/A",
  "out": "视频/V_S03_t2.mp4",
  "references": [
    {"path": "起始帧/F_S03_t1.png", "role": "first_frame", "label": "S03 起始帧",
     "may_control": ["开场构图", "起始姿态"], "must_not_control": ["终点姿态", "尚未发生的动作"]}
  ],
  "parameters": {"duration": 6, "resolution": "768P", "prompt_language": "en"}
}
```

`provider` 取 `minimax-video`、`seedance`、`minimax-speech`、`minimax-music`、`gpt-image-2`。`prompt` 逐字取自 shots.json 的 `video_prompt`（或剧本原句、配乐说明），不在 job 里改写。离线自测：`python3 $S/merged_selftest.py -k providers`。

## 来源

- MiniMax 视频生成 API：https://platform.minimax.io/docs/api-reference/video-generation-v2-create （2026-09-07 核对：必填时长、型号差异、输入模式互斥、data URI 与单文件上限）
- MiniMax T2A HTTP API：https://platform.minimax.io/docs/api-reference/speech-t2a-http （2026-09-25 核对：情绪取值、2.8 语气词、`<#x#>` 停顿、`pronunciation_dict`、`language_boost`）
- MiniMax 音乐生成：https://platform.minimax.io/docs/api-reference/music-generation
- 火山引擎视频生成 API：https://www.volcengine.com/docs/82379/1520757
- GPT Image 2：https://developers.openai.com/api/docs/models/gpt-image-2 ；generations / edits 接口参考同站
- 本地已合并的生产套件（适配器请求契约、任务号先落盘、失败三路）。
