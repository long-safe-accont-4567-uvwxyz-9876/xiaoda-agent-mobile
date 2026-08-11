# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260809-001] correction

**Logged**: 2026-08-09T23:10:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
移动端语义向量链路必须固定使用 SiliconFlow API。

### Details
不能把“远程 Embedding”泛化为任意 OpenAI-compatible 服务。记忆检索、工具检索和迁移脚本都必须禁止本地模型与其他远程端点；无 API Key 时关闭语义检索。

### Suggested Action
持续用生产文件扫描和构造函数门禁阻止 `EMBED_BASE_URL`、本地 Provider、模型资产及通用外部 Embedding 客户端复活。

### Metadata
- Source: user_feedback
- Related Files: memory/vector_store.py, tool_engine/tool_search.py, scripts/migrate_vector_dimensions.py
- Tags: mobile, embedding, siliconflow, api-only

### Resolution
- **Resolved**: 2026-08-09T23:10:00+08:00
- **Notes**: 运行时与文档固定 SiliconFlow，删除本地回退和可变 Base URL。

---
