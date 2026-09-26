# 审片证据与剪辑准入

## 状态和责任

文件已下载不表示质量合格；ASR 文本一致不表示台词语义、音色和表演已经听审。`auto` 只选择候选和给出 `pending_review`，不会因为命中率或缺少数据而新建 ok。已有、未失效的人工/模型审查可保留。

每个视频 take 在 `review.json` 的 `shots[镜号].video_takes[编号]` 中保存：

- `speech_diff`：文本插入、删除、替换及关键字疑点；`hit` 仅为双向相似度诊断。
- `assessment.checks.visual`：职责动作、人物身份、重要物件、揭示内容是否正确。
- `assessment.checks.audio`：旧字段，现在跟着 `asr_ok` 走（mark 写了 `--asr-ok` 时自动同步成 pass/fail）；听感和同步看下面的三项，不看它。无对白镜也要检查实际声音。
- `assessment.checks.continuity`：与相邻镜、该场持续状态和人物知情相容。
- `assessment.evidence`：所看/所听的位置、动作与判断依据。
- `video_takes[n].must_show_check`（`mark --must-show MS1=pass|fail|unverified` 写入，并镜像到镜级 `must_show_check`；读时以 take 级为准）：本镜 `must_show_ids` 每条事实在当前 take 里 `pass` / `fail` / `unverified`；有 `fail` 时 mark 拒绝 `ok` / `weak`、auto 给 retake、正式剪辑拒绝，只能重拍或回剧本、分镜改；`unverified` 脚本不拦，但审片规则要求承担镜进正式剪辑前核成 pass（production-and-review §5、§5c）。
- 声音结论拆三项，写在 `assessment` 里：`asr_ok`（识别正确，ASR 逐字比对）、`listen_ok`（听感自然，真的听过）、`sync_ok`（口型同步），都是 true/false/null（`mark --asr-ok / --listen-ok / --sync-ok`）。null 显示为"未验证"，不得汇总成"通过"。入剪要求 `asr_ok` 为 true；`listen_ok` 或 `sync_ok` 为 false 时拦下，null 放行但处处标"未验证"。旧记录只有 `checks.audio: pass` 时只算 `asr_ok: true`，另两项为 null。
- `assessment.action_window`：该 take 实测的职责动作开始/结束秒。镜头声明 `action_required`、`planned_action_window` 或旧 action_window 时必需。
- `assessment.speech_window`：该 take 必要对白从首音到末音的实测区间。有对白且不用替代音源时必需；被引用作 audio_from 的音源也必需。
- `assessment.media_sha256` 与 `shot_sha256`：工具自动绑定当前素材字节与镜头规格；换文件、改镜头后审查失效。
- `edit`：该 take 自己的 in/out/mode/speed，换 take 不继承旧剪点。

三项 checks 为 pass/fail/pending。`ok` 要求全部 pass、`must_show_check` 没有 fail（脚本强制；unverified 由审片人核掉），且证据/必要时段齐全；`weak` 还需明确接受非关键缺陷的 acceptance_reason，不能豁免剧情动作或错误台词。`mute` 不能移除必需对白，除非存在已审替代音源。`retake` 表示待修复，仍不能进入正式剪辑。

## 怎样记录

以下是命令形式示例，数值和证据必须来自实际查看/听审，不能照抄示例冒充已审。短接触事件用更密抽帧或播放核对，2fps 接触表可能漏掉瞬间。

```text
python3 scripts/review_tool.py mark PROJECT EP001 EP001-S01 --video-take 1 --visual pass --asr-ok true --listen-ok true --sync-ok null --continuity pass --must-show MS1=pass --action-window 1.0 3.0 --speech-window 0.5 2.6 --evidence "t1：1.0–3.0 秒先接后放；对白逐字听过；持物与反打一致" --verdict ok
python3 scripts/cut.py PROJECT EP001 --dry-run
python3 scripts/cut.py PROJECT EP001
```

无对白镜不填 speech-window；不承担动作时段职责的静态镜不必为填字段补动作。真实缺陷使用 fail 或 pending。更改审查项需要新的 evidence。改变播放速度后重新听审该速度；工具不会把旧听审自动沿用到新速度。

正式 cut 在执行媒体命令前验证准入；未审、失效、retake、缺失素材、无说明遗漏镜头均阻断。按 cut_order 去掉的独立音源由引用关系说明；其他删镜用 drop 并写 note，仍由创作者判断是否损害叙事。

需要先看整集时：

```text
python3 scripts/cut.py PROJECT EP001 --draft
```

草剪默认输出 `审查/EP001-草剪.mp4`，写 `草剪单.md`；不覆盖正式成片。草剪含未审素材，不能作为正式交付依据。

## 时序与旧项目兼容

`shots.json.planned_action_window` 是生成前的估时；旧镜头级 action_window 也只当计划。运动能量 action_start/end 是候选，均不直接作为正式剪点。核对具体事件后用 mark 写到当前 take 的 assessment。正式剪辑在所有模式下保护已审动作和对白区间的两端。

旧 review 中只有镜头级 ok、note 或剪点，不自动升级为新证据。保留旧记录，按当前所选素材补录三项审查与时段。缺少听音能力时保持 pending，可出草剪，不能伪造 audio pass。文件哈希证明证据关联到哪份素材，不证明审查者判断本身正确。

ASR 失败/输出缺行不会被记作无声；识别差异先听审，不按固定分数自动付费重拍。`readings` 只接受已确认的读音等价，不用它抹掉否定、数量、身份或剧情事实。旧 `budget.asr_pass` 不再决定准入或自动重拍。
