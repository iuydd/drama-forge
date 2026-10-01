> **仅供旧项目兼容。**下面保存 4.3 外部 Brain 的消息流程，不是 4.5.0 默认入口。默认由当前 agent 按现行章节完成前期，再使用 assemble / validate / bind。只有用户明确要求旧外部分工时才启用本页；`prepare` 的请求还须显式写 `legacy_brain_compatibility: true`，表示使用历史载荷。旧文中的强制首帧、旧创作规则和 ChatGPT 默认通道不可自动带入新项目。

# 外部 Brain 兼容工作流｜4.3 upfront_only

## 正常运行顺序

1. **盘点。**恢复用户指定集数、原著/简报、固定设定、现有资产、实际媒体后端和质量规格，核用户授权预算与可用大脑通道。只把有必要的项目资料发送给大脑，不发密钥、cookie、私钥、整份本地目录或无关隐私。
2. **发消息。**发送`assets/brain-skill.md`（大脑指令）、`prompts/agent-to-brain.txt`（本次任务）和`prompts/record-format.txt`/response schema。任务JSON代入{{PROJECT_REQUEST_JSON}}；有已配置授权的聊天连接器就调用其真实发送/取回工具，不假装这份Skill自己是连接器。通道必须保持会话/请求ID、完整输出、结束状态与调用额度。
3. **收齐。**按manifest收齐所有episode/world/asset/task/repair/delivery。PARTIAL时自动发续收模板，不要求用户说“继续”；固定记录和版本不变。单条截断JSON不能当完整分块。格式/漏项/设计矛盾只在前期有限修复，计入同一调用预算；额度用尽停。不可让agent自行补写缺失剧情。
4. **验证前期计划。**完整剧本、每镜首帧/视频prompt、每个新资产的生产任务、依赖无环、全范围覆盖、已锁规格/状态、风险标准和有限替代分支齐备。PLAN_COMPLETE不是生成许可；execution_blockers、媒体能力与费用授权另查。全部指定集数前期完成后才开始图片任务。
5. **自动制作。**生成角色/空间/道具母版→真实G1→首帧/必要预演→G1/G0→视频/声音→G2→定向预案返修→实际剪辑/非相邻回访G3→终片G4。由生产审核者与隔离盲看实际看媒体，不请求前期大脑审片。把接受媒体写入accepted-asset-registry，候选/未知不得登记为已接受。
6. **自动推进。**保护域按前期recipe绑定当前文件/哈希，产出execution-packet-1，核原4.2媒体门禁/精确原生参数/能力/预算再提交；每次使用新实际输出都需要本地真实验收。按原10章与真实项目配置调度。到交付前不例行向大脑发制作消息。
7. **失败。**先查错输入/版本/接缝，选择预写的完整替代分支；换take/修字/配音/局部合成共用失败链额度。分支不覆盖、必检UNKNOWN、原请求状态未知、权限/能力不足即暂停相关任务并向用户报告。不能为实现“全自动”让坏片通过、无限重生或自由改台词/机位。

## 文本通道两条路线

**已授权连接器**：agent自行调用真实可用的发消息和取回复接口，保持会话关联。必须实测它能发送完整大脑规则/项目资料、取回完整JSON/附件文本、区分完成/截断/拒绝。只拿页面某一段文字不够；不要绕过登录、验证码或平台访问限制。未配置时状态BRAIN_TRANSPORT_UNAVAILABLE，不静默换用收费API。

**可选OpenAI Responses API参考客户端**：`brain_transport.py`用明确指定的可用模型，只提供文本输入且tools=[]，输出JSON再本地校验。无默认模型、无自动选更便宜模型；它调用配置的API模型，不是接管当前ChatGPT聊天，也不自动继承此聊天记忆或套餐。授权、凭证与模型兼容性由实际宿主先配置。此包未执行真实API请求。

**可选桌面通道**：仅在本次明确选择并授权时使用，核实当前应用、模型及工具能力，按[桌面通道](brain-chatgpt-desktop.md)发送与取回；历史设置不构成当前授权。

```bash
# 在Skill根目录；project-request.json须包含真实资料，不沿用模板占位。
python tools/production-ops/scripts/preproduction.py prepare --request /project/project-request.json --out /project/brain-message.json
# 用已授权连接器发送brain-message.instructions/input；或显式授权API调用：
python tools/production-ops/scripts/brain_transport.py --request /project/project-request.json --model ACTUAL_VERIFIED_API_MODEL --max-calls APPROVED_CALL_CAP --max-output-tokens VERIFIED_OUTPUT_CAP --state-dir /protected/brain-requests --out /project/preproduction-plan.json --allow-brain-api
# 连接器路线收到多个合法分块后：
python tools/production-ops/scripts/preproduction.py assemble --request /project/project-request.json --parts /project/part1.json /project/part2.json --out /project/preproduction-plan.json
python tools/production-ops/scripts/preproduction.py validate --plan /project/preproduction-plan.json
# 已生成并由本地审核者接受输入后：
python tools/production-ops/scripts/preproduction.py bind --plan /project/preproduction-plan.json --registry /project/accepted-assets.json --root /project --task TASK_ID --out /project/bound-task.json
```

命令中的大写占位必须用真实已核实参数替换。API客户端只负责收集前期文本，不自动启动图片/视频；生产由agent继续执行。输入超限不悄悄截断或丢原著，先在授权范围分段读原文并保持出处/全弧覆盖，超出额度就报告。格式修复模板由连接器协调器使用；参考API客户端对拒绝、截断或格式错误安全停止，不自动猜补。

## 权威分开

前期大脑＝设计决定；生产审核者＝实际媒体接受；受保护宿主＝原方案一致性/精确请求签名与预算；主执行agent＝执行与有界分支选择。旧4.2的逐阶段大脑批准模式不是本默认模式。更改发布版本不等于更改底层schema，现有媒体policy_version仍为4.2.0并全部启用。

版本字段：分发包package_version=4.3.3，工作流workflow_version=4.3.0，原文content_version=3.1.2-public。兼容旧媒体工具的metadata.version与policy_version继续为4.2.0；该字段历史含义是媒体规则版本，不表示本包仍使用逐阶段大脑流程。禁止仅改政策数字绕开原门禁。

用户user_brief原样传递；项目摘要不得新增创作偏好或删去用户已给要求。记录格式仅是载体，不能代替或降低原文STORY/G3。
