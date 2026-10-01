# 配套工具

仅在任务需要时使用。脚本提供离线规划、数据检查和媒体处理；不自带生成服务、凭证、ASR/TTS或真实语义审查。

- `tools/short-drama-writer/`：创作结构、项目记录和通用示例。
- `tools/reference-builder/`：参考素材清单、真实文件与输入关系检查，不绑定图像模型。
- `tools/visual-continuity-prompter/`：场景连续性、提示词、像素保护与审核记录。
- `tools/production-ops/`：调度、阅读包、账本、音频记录、剪辑时间线与门禁。

机器阅读使用 [source.md](../assets/source.md)和[阅读地图](../config/stage-reading-map.v3.json)，不传短入口。新版本需要真实重绑，初始阅读凭据不表示已读。未连接适配器时只能报告计划或结构结果。

运行前按当前项目填写 `model-routing.json`、`runtime-profile.local.json`、`execution-policy.json` 与 `PROJECT_START.md` 等模板。模型/声线 ID、服务、能力证据、资源池和费用政策均来自本次实际配置；不存在公共的个人默认值。不要把凭证值写入这些文件。

调度工具每次只处理指定 `active_episode`；`pools.capacity` 是本次获准容量，须同时满足实际资源上限。模型检查根据已绑定型号、模态、能力验证与上下文隔离判断，不按价位分档。手机副本规划必须明确提供当前通道字节上限：

```bash
python3 tools/production-ops/scripts/execution_control.py mobile-plan --help
```

字幕/UI 使用同一时间线的 `presentation`：

```bash
python3 tools/production-ops/scripts/presentation_checks.py --timeline /project/edit/edit-timeline.json
```

它只检查已声明关系、时间映射与保护区域，不推断遗漏的因果、不听音、不识脸、不渲染。实际合成器需消费派生安排，记录输入并审核真实输出。工作母版 `presentation_applied=false` 不能算完成后期的成片。原 G3 同版观察完整事件，声明和文件哈希不替代实际观察。

首次部署或修改工具时运行相关离线检查；稳定生产仅运行适用门禁。样例状态与合成测试不能当作真实项目的审核通过。公开模板中的经验日志为空，由使用者在自己的项目中记录。


## 按本次命令准备依赖

在现有工具准备环节检查本次需要的依赖，沿用项目选定的 Python 环境，不新增制作关卡：

| 本次操作 | 需要的外部依赖 |
|---|---|
| 正文、阅读包、提示词编译、记录与结构门禁 | Python 标准库 |
| 像素合成/保护区检查、读取图像尺寸 | Pillow |
| 运行可选 JSON Schema 校验 | jsonschema |
| 媒体探测 | ffprobe |
| 音视频处理与实际导出 | ffmpeg、ffprobe |

使用同一个 Python 运行下面的探测，按需组合操作。纯文本用 `text`，不查媒体依赖。它只报告本机可发现的依赖，不安装、不连接服务，也不证明媒体处理或生产审核通过。

```bash
python3 scripts/check_dependencies.py text
python3 scripts/check_dependencies.py image schema
python3 scripts/check_dependencies.py media
```

## 维护公开文档

模块正文直接维护 `references/00–11` 和 `references/blind-review.md`；它们是现行内容来源。阅读模块组合维护 `config/stage-reading-map.v3.json`。入口说明和使用说明各自维护；不要手改派生的 `assets/source.md`、路线表或模板地图，也不要拿 `assets/legacy-*` 覆盖现行规则。

```bash
python3 scripts/sync_skill.py --write
python3 scripts/sync_skill.py --check
```

同步工具将 13 份现行章节拼成工具全文，刷新阅读路线、内容 hash 和模板地图。版本只在 `SKILL.md` 的 `metadata` 维护：`version` 与 `package_version` 一致，`content_version` 可单独标明内容版本；同步更新机器阅读配置、全文版本和 README 的“当前版本”标记，其余 README 正文仍手工维护。字段缺失、重复或格式不明时先报错，不写入部分结果。它不登记阅读回执；规则内容变化后仍需重新绑定凭据。维护完成后运行 `python3 scripts/run_tests.py --report /absolute/test-report.json`；测试结果只代表离线检查，不代表已生成或看过成片。
