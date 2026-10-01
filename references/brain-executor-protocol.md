# 前期大脑—自主生产协议｜4.3.0

兼容说明：本页描述外部 Brain 协议。4.5.0 默认由同一个 agent 完成前期，brain 等字段名保持接口兼容。显式使用外部 Brain 时，它只输出前期文本，生产阶段不等待它接受参考图；请求模板为[agent-to-brain](../prompts/agent-to-brain.txt)。前期续收和格式修复与制作返修不是一回事。

## 设计交付

一个逻辑前期阶段覆盖用户指定的全部集数。agent发送已核实项目资料与完整大脑规则，收齐manifest全部记录，经preproduction.assemble/plan_errors核scope、完整性、DAG、逐镜任务、资产生产者、state/风险与精确提示词。它只能证明显式数据符合要求，不能自动证明故事好看或任意语义正确。大脑在交付前自行综合审读；实际后端未知需execution_blockers，不谎报能执行。

## 执行批准不是伪造大脑审片

`execution-packet-1`（workflow_version=4.3.0，workflow_mode=upfront_only）由**production_supervisor**登记，policy_version=4.2.0。它绑定preproduction_plan、accepted-asset-registry、plan_task_id、精确request、request_sha256、当前semantic_review、实际reviewed_inputs、fidelity/continuity及native_request_sha256。`brain_media_review_performed=false`必须保留。

brain_handoff.load_task新增显式分支：按前期recipe重新绑定真实资产并逐字段比较请求；仍执行4.2的文件/输入审核记录/语义/连续性/fidelity验证。不能把decision_owner写chatgpt_brain来假装我看过。旧brain-packet-1原逻辑保留供旧项目，不能拿旧模式绕过新默认边界。

受保护宿主保留真实大脑文本/通道回执并登记plan hash，worker不能改完plan后自签。宿主按原任务或明确已触发的有限repair分支签**精确运行请求**，每次核当前媒体/能力/费用门禁；不是每次请大脑发消息。trusted_runtime旧purpose字段creative在此表示“与前期设计相符的执行授权”，不表示有人再次看片；budget仍独立。签名密钥与服务凭证不放agent可读目录。

## 实际接受与返修

资产注册表只收生产审核者真实接受且附有同版观察证据的媒体。候选/哈希通过/能解码不等于接受。每个输入先核当前身份/状态/机位/用途与谱系；失效后代重新审核，不把坏尾帧接龙。G0–G4、准确字/动作/眼神/语气、实际切点与非相邻回访继续执行。

生产绑定期间只选择预写完整分支和已授权无损技术替代，不临场改剧情或任意扩 prompt。分支触发必须有实际观察，依赖重绑/重验仍在同失败链预算内。无分支或未知硬项暂停相关段；若确认前期方案有误，当前 agent 可回前期修订并重新校验，注明失效范围。新增创作方向仍按用户要求；旧片与旧 PASS 不能只改 hash 假装通过。

具体安装与未部署边界见[部署](deployment.md)，格式见[交接格式](handoff-format.md)。
