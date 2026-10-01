
## 自动交接格式（不是另一套创作要求）

agent提供本文件全文、用户原始项目请求、记录格式与响应schema。保留用户原话及已锁定事实，不自行追加项目偏好。按原文先写自然正文，再装入JSON；格式只承载原版要求，不替代原版审读。

响应为brain-preproduction-response-1：workflow_mode=upfront_only，project_id/request_id/plan_id/revision/episode_ids/status/part_index/manifest/records/assumptions/execution_blockers/invalidates按随附schema。manifest列全计划{id,kind,episode_id}；records为{id,content}，content是该记录完整JSON对象的序列化字符串。kind为world/episode/asset/task/repair/delivery；正文保留自然段。

world保存设定与事件状态；episode保存完整正文、准确台词和全部镜头、声音剪辑方案及按原文得到的验收目标；asset声明实际已有来源或生成任务；task给完整最终prompt、输入职责/参数、依赖、起终状态和成功证据；repair引用完整替代task、触发、保留项、复核范围和上限；delivery列全范围集数及制作验收交付安排。字段名与实际接口以agent随附格式为准，不能据字段例子改戏。

一次放不下用PARTIAL，每个record本身完整；后续只补缺失record，同一manifest与版本，最后一块COMPLETE。缺项不能用“后续同理”或COMPLETE状态掩盖。格式/缺项修复只在前期完成，不是媒体返修。全部指定范围收齐后agent才开始制作。

未来输入只写{"$asset":"稳定资产ID","field":"file"}或path/sha256槽；最终prompt须写完整，不留下让agent自由补写的文本。接口确需configuration_sha256时使用COMPUTE_FROM_EXECUTION_TEMPLATE，执行端据完整模板和真实输入计算。已有锁定文本不得随绑定改写；未核实工程参数列execution_blockers。

这部分只适配原一体版的角色、前期一次性交付与机器传输。以下原文是唯一理论正文，后面不追加精简版、风格覆盖或重写后的自查标准。

