# 设计依据与证据边界

外部资料查阅日期：2026-09-29。规则不限于一个厂商；具体后端需用当前实际配置验证。

- Google Cloud / Vertex AI，Video generation best practices：图生视频中输入图已提供外观/场景信息，提示词侧重运动；对白格式等建议仅适用于相应Veo路径，不推广为所有模型的唯一格式。https://cloud.google.com/vertex-ai/generative-ai/docs/video/best-practice
- Anthropic，Skill authoring best practices：渐进读取、先真实任务评测再增加说明，避免用冗长规则代替有效性验证。https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices

本包的工程行为由源码、合成回归及实际本地媒体冒烟记录支持。真实模型/审阅者准确率、观众审美、质量非劣性、token与产出成本改善需用户当前环境的独立数据，当前为NOT_RUN。引用官方建议不等于已验证用户后端。

## 4.3 可选文本API通道核对（2026-09-29）

- OpenAI Structured Outputs： https://developers.openai.com/api/docs/guides/structured-outputs — Responses API的text.format JSON模式；JSON模式不能代替本地schema/完整性/语义校验；检查completed/incomplete/refusal。
- OpenAI账单说明： https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform — ChatGPT与API平台的账单/订阅分别管理。不从聊天套餐推断免费API调用。

此包仅实现参考客户端，不指定某个当前模型一定支持该配置；实际账户/模型与参数先验证。没有执行外部请求。
