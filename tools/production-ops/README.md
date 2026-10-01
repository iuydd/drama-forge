# 生产闭环工具

本目录是 Skill 自带的离线工具，不需另装 Skill，不联网或提交模型任务，也不自动安装模型及依赖。

- `dialogue_audit.py` 比对逐字转写与声源记录；不是 ASR 或听音工具，退出 0 只表示记录一致。
- `job_ledger.py` 汇总已有账本。集成使用 `Ledger.prepare/record_authorization/claim_submission/attach_remote/reconcile/settle`，调用方接入真实授权事件和任务查询。
- `media_tools.py` 的 `animatic` 用真实静帧和临时音轨渲染预演，保持画幅且不覆盖；`extract-audio` 提取独立 16k 单声道 ASR 副本；`loudness` 用 FFmpeg 测量响度，听感仍须验收。
- `production_gates.py` 核对文件、快照、逐句/逐镜覆盖与阶段报告，和原视觉门禁共同使用。

上述脚本在 `scripts/`，参数以各脚本的 `--help` 为准。

null、空数组、NOT_RUN、DRAFT/UNKNOWN 不表示完成。记录校验不证明授权真实、媒体合格或能力接通，报告须来自实际检查。金额用币种最小单位整数，未知价格不填 0；授权、未知提交、幂等与费用边界见 [10 执行](../../references/10-execution.md#r10)。

在本目录运行 `python3 -m unittest discover -s scripts -p 'test_*.py' -v`。合成记录、FFmpeg 色块和测试音只验证工具，不验证真实剧本、视频模型或 ASR 效果。

`presentation_checks.py --timeline edit-timeline.json` 从已采用事件解析字幕/UI位置，由 `edit_timeline.validate` 和 `production_gates` 调用。格式见 `examples/edit-presentation.planned.json`、`templates/edit-production-reports.json`；观察仍放原 edit_cut_review，不新增模型审核。

工具只核显式范围/依赖、保护区与证据绑定，不提供 ASR、UI 排版、脸部跟踪、平台生成或语义判断。基础 render 只出未叠字母版；合成与同版验收见 [11 交接](../../references/11-handoff.md#r11)。示例不代表真实项目已审核或修复。

`brain_handoff.py` 绑定冻结包与真实请求；`fidelity_contract.py` 在原门禁核对方向、视线、动作结果、文字、表面位置及语气转折的证据。批准包权限与提交拦截须宿主接入，兼容协议见 [Brain 执行协议](../../references/brain-executor-protocol.md)。
