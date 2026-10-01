# 前期与运行时数据格式｜4.3

## project request与大脑响应

project request必有project_id/request_id/user_brief/episode_ids/source_texts/existing_assets/media_profiles/quality_limits。source_texts给实际原著/版本/完整情节弧；existing_assets只放确实存在且可用的资产记录，不放凭证。集数、规格、调用额度和通道来自真实用户授权。模板见[project-request](../templates/project-request.json)。

响应外层按[JSON Schema](../schemas/brain-response.schema.json)；记录语义按[record-format](../prompts/record-format.txt)。每一块完整合法JSON，content再次解析为对象，拒绝重复键/NaN。manifest与计划身份固定；同块重复同内容幂等，冲突内容/版本/集数拒绝。收齐指定全部记录且最后一块COMPLETE才PLAN_COMPLETE。BLOCKED和INCOMPLETE不得生产。

组装后的`preproduction-plan-1`含原请求、全记录、响应部分摘要和execution_blockers；media_approved=false/spending_authorized=false。完整剧本与每镜两类prompt、新资产生产者和无环依赖由校验器检查。高级审美/物理/任意自然语言不能由schema证明。

## 运行时只绑定已声明槽

`{"$asset":"ID","field":"file"}`解析为真实{path,sha256}；path/sha256可单独取。同一个asset ID必须有真实同版接受；不能从候选中挑一张就直接声称通过。此机制不允许向最终prompt插入自由文字/执行任意表达式。

`accepted-asset-registry-1`的assets每项：asset_id、file、review。review文件含status=ACCEPTED、精确subject={path,sha256}、reviewer_role=production_reviewer或independent_reviewer、reviewer_id、具体observation、full_required_scope_observed=true、实际evidence文件列表。它是本地观察声明，仍必须由受保护审核流程和4.2真实门禁验证；不是签名/图像识别器。

recipe.request_template是大脑前期给出的完整请求文本、输入槽与质量参数；execution_template可给完整scene/shot/runtime_profile模板。configuration_sha256标COMPUTE_FROM_EXECUTION_TEMPLATE时，binder真实计算4.2 request_snapshot并比较全部字段；brain_binding仍是避免循环hash的外部字段。

## execution-packet-1

待填模板见[execution-packet](../templates/execution-packet.json)。它默认DRAFT/PENDING/NOT_RUN，宿主完成实际绑定、观察和受保护批准后才改状态；模板本身不能提交。

共同字段沿用旧packet的packet_id/revision/episode_id/phase/status=LOCKED/example_only=false/approval_evidence/reviewed_inputs/blocking_questions=[]/tasks。新字段：workflow_version=4.3.0、workflow_mode=upfront_only、decision_owner=production_supervisor、brain_media_review_performed=false、preproduction_plan={path,sha256}、asset_registry={path,sha256}。policy_version=4.2.0是现有媒体校验器版本，不改名伪装新的媒体实现。

每task加plan_task_id，保留request/request_sha256/native_request_sha256、semantic_review、适用fidelity_contract/continuity_plan。brain_handoff重新读取完整前期plan并机械bind，任何正文/prompt/输入/参数超出recipe都阻断。semantic_review是**生产审查者**对当前实际绑定/状态/参考/后端的观察记录，不假装前期大脑再次查看。

现有BoundProductionValidator完整组合仍支持video/pre_video；其他图像/声音/后期入口由用户真实宿主注册并实测对应门禁，不编造已接入的通用接口。前期文字完整不意味着厂商入口已经安装。

## 生产状态与有限分支

asset pending/observed/accepted保存在生产工作区，不例行回大脑。原brain-return-2工具只用于旧交互项目或人工调试，不是新默认等待点。repair引用完整替代task，协调器核实际触发、replaces、preserve、recheck、max_attempts与共同预算；未触发分支不得当普通ready任务并发生成。交付完成要真实终片G4，不能只因为所有task声明完成就发布。
