---
name: Dify RAG 检索优化计划
overview: 解决 Dify 知识库检索返回"未匹配"的问题，通过降低分数阈值、优化查询改写策略、添加调试日志、调整检索参数等方式提升召回率。
todos:
  - id: add-debug-logs
    content: 添加调试日志到rag_search函数，打印Dify返回的原始记录数和分数
    status: completed
  - id: adjust-retrieval-params
    content: 调整检索参数：禁用分数阈值、增加top_k、使用语义搜索
    status: completed
    dependencies:
      - add-debug-logs
  - id: optimize-query-rewrite
    content: 优化查询改写：短问题跳过改写，添加原始查询回退机制
    status: completed
    dependencies:
      - add-debug-logs
  - id: test-improvements
    content: 测试改进效果：用简单问题验证检索是否成功匹配文档
    status: completed
    dependencies:
      - adjust-retrieval-params
      - optimize-query-rewrite
  - id: update-dev-log
    content: 更新开发日志，记录改进内容和测试结果
    status: completed
    dependencies:
      - test-improvements
---

## 用户需求

解决Dify知识库检索返回"未匹配"的问题，即使知识库中存在相关文档（如"公司的核心价值观是什么"、"公司核心优势"、"告诉我公司的基本信息"）。

## 问题现象

用户提出简单直接的问题时，系统返回"知识库中未检索到相关内容"，但Dify知识库中明明有对应文档和匹配内容。

## 核心改进目标

1. 提高检索召回率，确保相关知识库文档能被正确检索到
2. 优化查询改写策略，避免引入语义噪声
3. 添加调试日志，便于诊断检索问题
4. 使系统对简单问题更加友好，减少误判

## 技术栈选择

- 编程语言：Python 3.x（基于现有项目）
- 框架：LangChain、LangGraph（现有项目已集成）
- API：Dify API（现有集成）
- 日志记录：Python print函数（与现有项目一致）

## 实现方法

### 问题根因分析

基于代码审查和问题描述，确定以下可能原因：

1. **分数阈值过高**：当前`score_threshold: 0.3`可能过滤掉相关性较低但仍有用的文档
2. **查询改写引入噪声**：`rewrite_query`将简单问题改写成复杂查询，导致语义偏移
3. **混合搜索参数不适合简单问题**：`hybrid_search`的权重设置可能不适合所有问题类型
4. **缺少调试信息**：无法看到Dify返回的原始记录和分数，难以诊断问题

### 解决方案设计

#### 1. 调整检索参数（提高召回率）

- **降低分数阈值**：将`score_threshold`从0.3降低到0.0（禁用阈值）或0.1
- **增加候选文档数**：将`top_k`从5增加到10
- **尝试不同搜索方法**：对简单问题使用`semantic_search`或`fulltext_search`，而非`hybrid_search`
- **暂时禁用重排序**：设置`reranking_enable: False`，观察是否提高召回率

#### 2. 优化查询改写策略

- **短问题跳过改写**：对于长度≤10字符或词汇数≤3的问题，直接使用原始查询
- **添加回退机制**：如果改写后的查询检索不到结果，自动使用原始查询重新检索
- **改写失败处理**：已存在回退逻辑，确保改写失败时使用原始问题

#### 3. 添加调试日志

- 在`rag_search`函数中打印Dify API返回的原始记录数和分数
- 打印每个候选文档的来源和分数，便于分析
- 在`rewrite_query`函数中打印原始问题和改写后的问题

#### 4. 增强错误处理

- 当检索结果为空时，尝试使用不同的检索参数重新检索
- 添加多层回退策略：改写查询→原始查询→降低阈值查询

## 实现要点

### 修改文件：`agents/rag_agent.py`

#### 调整检索参数

将`rag_search`函数中的检索参数调整为：

```python
"retrieval_model": {
    "search_method": "semantic_search",  # 对简单问题使用语义搜索
    "reranking_enable": False,           # 暂时禁用重排序
    "top_k": 10,                         # 增加候选文档数
    "score_threshold_enabled": False,    # 禁用分数阈值
}
```

#### 优化查询改写

在`rewrite_query`函数开头添加短问题判断：

```python
def rewrite_query(llm, question: str) -> dict:
    # 短问题或关键词型问题跳过改写
    if len(question) <= 10 or len(question.split()) <= 3:
        print(f"[QueryRewrite] 问题较短，跳过改写: {question}")
        return {
            "rewritten_query": question,
            "keywords": [],
            "sub_questions": [question],
        }
    # 原有改写逻辑...
```

#### 添加调试日志

在`rag_search`函数中添加：

```python
print(f"[DifyRetrieve] 查询: {search_query}")
print(f"[DifyRetrieve] 返回记录数: {len(records)}")
for i, record in enumerate(records):
    score = record.get("score", 0)
    source = record["segment"]["document"]["name"]
    print(f"[DifyRetrieve] 记录{i+1}: 分数={score:.3f}, 来源={source}")
```

#### 添加回退机制

在`rag_search`函数中，当检索结果为空时，尝试使用原始查询：

```python
if not records:
    print(f"[DifyRetrieve] 改写查询未找到结果，尝试原始查询: {query}")
    resp = requests.post(
        f"{DIFY_BASE_URL}/datasets/{DIFY_KB_ID}/retrieve",
        headers={...},
        json={
            "query": query,  # 使用原始查询
            "retrieval_model": {...}
        }
    )
    records = resp.json().get("records", [])
```

## 架构设计

本改进主要涉及`agents/rag_agent.py`中的`rag_search`函数和`rewrite_query`函数，不需要大的架构变更。为了保持代码的模块化和可维护性，建议将检索参数提取为配置常量，便于调整和测试。

## 目录结构

主要修改文件：

- `agents/rag_agent.py`：[MODIFY] 调整检索参数、优化查询改写、添加调试日志、增强回退机制
- `project_documents/Dev_log.md`：[MODIFY] 更新开发日志，记录改进内容和测试结果

## 关键代码结构

1. 检索参数配置（建议在文件顶部定义常量）：

```python
# 检索参数配置
DEFAULT_SCORE_THRESHOLD_ENABLED = False  # 禁用分数阈值
DEFAULT_TOP_K = 10                       # 增加候选文档数
DEFAULT_SEARCH_METHOD = "semantic_search" # 默认使用语义搜索
DEFAULT_RERANKING_ENABLE = False         # 暂时禁用重排序
```

2. 查询改写优化：

```python
def should_skip_rewrite(question: str) -> bool:
    """判断是否需要跳过查询改写。"""
    # 短问题或关键词型问题跳过改写
    return len(question) <= 10 or len(question.split()) <= 3
```