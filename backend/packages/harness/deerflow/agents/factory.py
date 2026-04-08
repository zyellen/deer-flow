"""
DeerFlow Agent 工厂模块 - 用前端思维理解

想象一下，你要创建一个智能聊天组件：
```
function ChatAgent({ model, tools, features }) {
  // 1. 准备工具集（API 调用函数）
  // 2. 配置中间件（请求/响应拦截器）
  // 3. 组装成可用的 Agent 组件
}
```

create_deerflow_agent 就是这样的一个"组件工厂"：
- 接收纯 Python 参数（类似 React props）
- 不依赖 YAML 配置或全局状态
- 位于底层 langchain.agents.create_agent 和高层 config-driven 工厂之间

比喻理解：
- 这就像 React 的高阶组件(HOC)模式
- 输入：基础配置（model、tools）
- 处理：层层包裹中间件（类似 Redux middleware chain）
- 输出：一个完整的、可运行的 Agent 实例
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from deerflow.agents.features import RuntimeFeatures
from deerflow.agents.middlewares.clarification_middleware import ClarificationMiddleware
from deerflow.agents.middlewares.dangling_tool_call_middleware import DanglingToolCallMiddleware
from deerflow.agents.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware
from deerflow.agents.thread_state import ThreadState
from deerflow.tools.builtins import ask_clarification_tool

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


# =============================================================================
# TodoMiddleware 系统提示词配置
# =============================================================================
#
# 比喻理解：
# 这就像给 AI 组件设定"内部工作规范"
# - 类似于 React 组件的 JSDoc 注释 + 类型约束
# - 告诉 AI 什么时候、如何使用 todo 列表工具
#
# 类比前端：
# 就像你在代码审查规范里说：
# - "复杂功能（3+ 文件改动）必须写实现计划"
# - "完成一个任务立即标记，不要最后统一标记"
# =============================================================================

_TODO_SYSTEM_PROMPT = """
<todo_list_system>
你可以使用 `write_todos` 工具来管理和跟踪复杂的多步骤任务。

**关键规则（类比代码规范）：**
- 完成一个步骤立即标记，不要最后批量标记 —— 就像提交代码要频繁 commit
- 任何时刻只能有一个任务处于 `in_progress` 状态 —— 就像单线程执行
- 实时更新 todo 列表 —— 就像实时保存用户输入
- 简单任务（少于 3 步）不要用这个工具 —— 就像简单改动不用写设计文档
</todo_list_system>
"""

_TODO_TOOL_DESCRIPTION = "创建和管理结构化任务列表，仅用于复杂任务（3+ 步骤），简单任务直接完成即可"


# =============================================================================
# 公共 API：创建 DeerFlow Agent
# =============================================================================


def create_deerflow_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    middleware: list[AgentMiddleware] | None = None,
    features: RuntimeFeatures | None = None,
    extra_middleware: list[AgentMiddleware] | None = None,
    plan_mode: bool = False,
    state_schema: type | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    name: str = "default",
) -> CompiledStateGraph:
    """
    创建 DeerFlow Agent 主工厂函数 - 用前端组件思维理解

    【核心比喻】
    这就像 React 的高阶组件工厂函数：

    ```typescript
    function createSmartAgent({
      model,           // 使用的 LLM 模型（像选择 UI 组件库）
      tools,           // 可用工具集（像 API 函数集合）
      systemPrompt,    // 系统提示词（像组件的 defaultProps）
      middleware,      // 中间件链（像 Redux middleware）
      features,        // 功能开关（像 feature flags）
      planMode,        // 是否启用计划模式
      stateSchema,     // 状态类型定义（像 TypeScript interface）
      checkpointer,    // 持久化存储（像 localStorage 适配器）
      name             // Agent 名称（像组件 displayName）
    }): SmartAgent {
      // 组装逻辑...
    }
    ```

    【参数详解】

    model (BaseChatModel):
        聊天模型实例，类似于选择 GPT-4、Claude 等不同的"大脑"
        类比：const model = new ChatOpenAI({ model: 'gpt-4' })

    tools (list[BaseTool]):
        用户提供的工具列表，功能注入的工具会自动追加
        类比：const tools = [searchTool, calculatorTool, fileTool]
        就像给组件传入 API 调用函数

    system_prompt (str):
        系统消息，设定 AI 的角色和行为规范
        类比：组件的 defaultProps 或 Context 默认值

    middleware (list[AgentMiddleware]):
        **完全接管模式** — 如果提供，将精确使用这个列表
        不能和 features 或 extra_middleware 同时使用
        类比：const middleware = [thunk, logger, saga] // 完全自定义中间件链

    features (RuntimeFeatures):
        声明式功能开关，类似于前端的功能标志系统
        类比：const features = { sandbox: true, memory: true, vision: false }

    extra_middleware (list[AgentMiddleware]):
        额外的中间件，通过 @Next/@Prev 定位插入
        类比：在现有 Redux middleware 链中插入自定义中间件

    plan_mode (bool):
        启用 TodoMiddleware 进行任务跟踪
        类比：const [todos, setTodos] = useState([]) // 启用任务清单模式

    state_schema (type):
        LangGraph 状态类型，默认 ThreadState
        类比：interface ThreadState { messages: Message[]; metadata: any }

    checkpointer (BaseCheckpointSaver):
        可选的持久化后端，保存对话状态
        类比：const storage = createPersistedState('chat-session')

    name (str):
        Agent 名称，用于 MemoryMiddleware 等区分存储
        类比：<Agent key="customer-service" /> 的 key 属性

    【使用示例】

    ```python
    # 方式 1：使用 features 声明式配置（推荐，类似 JSON 配置）
    agent = create_deerflow_agent(
        model=gpt4,
        features=RuntimeFeatures(sandbox=True, memory=True),
        plan_mode=True
    )

    # 方式 2：完全自定义 middleware（高级，类似手写 Redux store）
    agent = create_deerflow_agent(
        model=gpt4,
        middleware=[MyCustomMiddleware(), AnotherMiddleware()]
    )
    ```

    Raises:
        ValueError: 如果同时提供了 middleware 和 features/extra_middleware
    """
    # ==========================================================================
    # 参数校验 - 类似于 TypeScript 的类型守卫
    # 确保不会同时传入冲突的配置方式
    # ==========================================================================
    if middleware is not None and features is not None:
        raise ValueError("不能同时指定 'middleware' 和 'features'，请二选一")
    if middleware is not None and extra_middleware:
        raise ValueError("不能与 'middleware'（完全接管模式）同时使用 'extra_middleware'")
    if extra_middleware:
        for mw in extra_middleware:
            if not isinstance(mw, AgentMiddleware):
                raise TypeError(f"extra_middleware 必须是 AgentMiddleware 实例，得到了 {type(mw).__name__}")

    # ==========================================================================
    # 准备工具和状态 - 类似于 React 组件的 props 默认值处理
    # ==========================================================================
    effective_tools: list[BaseTool] = list(tools or [])  # 用户提供的工具
    effective_state = state_schema or ThreadState       # 使用默认状态类型

    # ==========================================================================
    # 中间件组装策略选择
    # 类比：Redux store 的创建方式选择
    # - middleware 模式 = 完全自定义（高级用户）
    # - features 模式 = 声明式配置（推荐，像使用 preset）
    # ==========================================================================
    if middleware is not None:
        # 完全接管模式：直接使用传入的中间件列表
        # 类似于 const store = createStore(reducer, applyMiddleware(...customMiddlewares))
        effective_middleware = list(middleware)
    else:
        # 声明式模式：根据功能标志自动组装中间件链
        # 类似于使用 Redux toolkit 的 configureStore({ middleware: getDefaultMiddleware => ... })
        feat = features or RuntimeFeatures()
        effective_middleware, extra_tools = _assemble_from_features(
            feat,
            name=name,
            plan_mode=plan_mode,
            extra_middleware=extra_middleware or [],
        )
        # 工具去重：用户提供的工具优先
        # 类似于 Object.assign({}, defaultTools, userTools)
        existing_names = {t.name for t in effective_tools}
        for t in extra_tools:
            if t.name not in existing_names:
                effective_tools.append(t)
                existing_names.add(t.name)

    # ==========================================================================
    # 创建 Agent 实例
    # 类似于：return <Agent model={model} tools={tools} middleware={middleware} />
    # ==========================================================================
    return create_agent(
        model=model,
        tools=effective_tools or None,
        middleware=effective_middleware,
        system_prompt=system_prompt,
        state_schema=effective_state,
        checkpointer=checkpointer,
        name=name,
    )


# =============================================================================
# 内部函数：基于功能标志组装中间件链
# =============================================================================


def _assemble_from_features(
    feat: RuntimeFeatures,
    *,
    name: str = "default",
    plan_mode: bool = False,
    extra_middleware: list[AgentMiddleware] | None = None,
) -> tuple[list[AgentMiddleware], list[BaseTool]]:
    """
    根据功能标志构建有序的 "中间件管道" + 额外工具

    【核心比喻】
    这就像构建一个 Express/Koa 的中间件栈，或者 Redux 的中间件链：

    ```
    请求 → Middleware1 → Middleware2 → ... → MiddlewareN → Agent核心 → 响应
           ↓ 每个中间件可以：
           - 修改请求/响应
           - 添加副作用
           - 提前返回
    ```

    【中间件执行顺序】（共14个，按优先级排列）

    想象一下这是前端的数据处理流水线：

    0-2. Sandbox 基础设施层（ThreadData → Uploads → Sandbox）
         类比：请求进入前的文件系统初始化

    3.   DanglingToolCallMiddleware（始终启用）
         类比：清理上一次未完成的工具调用（类似清理上次的 pending 状态）

    4.   GuardrailMiddleware（guardrail 功能开启时）
         类比：内容安全检查（像输入验证中间件）

    5.   ToolErrorHandlingMiddleware（始终启用）
         类比：API 错误统一处理（像 axios error interceptor）

    6.   SummarizationMiddleware（summarization 功能开启时）
         类比：长对话自动摘要（像虚拟列表的窗口化）

    7.   TodoMiddleware（plan_mode=True 时）
         类比：任务追踪器（像 Redux 的 action logger）

    8.   TitleMiddleware（auto_title 功能开启时）
         类比：自动生成对话标题（像自动生成文件名）

    9.   MemoryMiddleware（memory 功能开启时）
         类比：用户记忆持久化（像 localStorage 同步器）

    10.  ViewImageMiddleware（vision 功能开启时）
         类比：图片预处理（像上传前的图片压缩）

    11.  SubagentLimitMiddleware（subagent 功能开启时）
         类比：并发子任务限制（像 Promise.all 的并发控制）

    12.  LoopDetectionMiddleware（始终启用）
         类比：死循环检测（像 React 的无限循环警告）

    13.  ClarificationMiddleware（始终最后）
         类比：澄清请求拦截器（像表单提交前的确认弹窗）

    【组装策略】
    1. 阶段一：按固定顺序构建内置中间件链
    2. 阶段二：通过 @Next/@Prev 定位器插入额外中间件

    【功能值处理方式】
    - False: 跳过该中间件（功能关闭）
    - True: 创建默认中间件实例（功能开启，使用默认配置）
    - AgentMiddleware 实例: 直接使用（自定义配置）

    【类比前端】
    这就像根据 feature flags 动态组装 Redux middleware：
    ```typescript
    const middlewares = [
      feat.logger && loggerMiddleware,
      feat.thunk && thunkMiddleware,
      feat.saga && createSagaMiddleware(),
      // ... 更多中间件
    ].filter(Boolean);
    ```
    """
    # 初始化中间件链和工具列表
    # 类似于：const middlewares = []; const tools = [];
    chain: list[AgentMiddleware] = []
    extra_tools: list[BaseTool] = []

    # ==========================================================================
    # [0-2] Sandbox 基础设施层 - 沙盒环境初始化
    # 类比：为每个请求创建独立的"运行时环境"，类似 iframe 或 Web Worker 的隔离
    # ==========================================================================
    if feat.sandbox is not False:
        if isinstance(feat.sandbox, AgentMiddleware):
            # 用户传入了自定义沙盒中间件
            chain.append(feat.sandbox)
        else:
            # 使用默认沙盒配置：线程数据 → 文件上传 → 沙盒执行
            from deerflow.agents.middlewares.thread_data_middleware import ThreadDataMiddleware
            from deerflow.agents.middlewares.uploads_middleware import UploadsMiddleware
            from deerflow.sandbox.middleware import SandboxMiddleware

            chain.append(ThreadDataMiddleware(lazy_init=True))  # 线程上下文初始化
            chain.append(UploadsMiddleware())                    # 上传文件处理
            chain.append(SandboxMiddleware(lazy_init=True))     # 沙盒执行环境

    # ==========================================================================
    # [3] DanglingToolCallMiddleware - 悬挂工具调用清理
    # 类比：处理上次的 "pending" 状态，确保状态一致性
    # 就像 Redux 中清理上次未完成的状态更新
    # ==========================================================================
    chain.append(DanglingToolCallMiddleware())

    # ==========================================================================
    # [4] GuardrailMiddleware - 内容安全护栏
    # 类比：输入验证 + 内容审核中间件
    # 就像表单提交前的校验规则检查
    # ==========================================================================
    if feat.guardrail is not False:
        if isinstance(feat.guardrail, AgentMiddleware):
            chain.append(feat.guardrail)
        else:
            raise ValueError("guardrail=True 需要传入自定义 AgentMiddleware 实例")

    # ==========================================================================
    # [5] ToolErrorHandlingMiddleware - 工具错误处理
    # 类比：API 错误统一拦截器（像 axios interceptors.response）
    # 把工具抛出的异常转换成友好的错误消息
    # ==========================================================================
    chain.append(ToolErrorHandlingMiddleware())

    # ==========================================================================
    # [6] SummarizationMiddleware - 对话摘要
    # 类比：虚拟列表的窗口化，只保留最近的 N 条消息
    # 长对话时自动摘要历史，避免超出 token 限制
    # ==========================================================================
    if feat.summarization is not False:
        if isinstance(feat.summarization, AgentMiddleware):
            chain.append(feat.summarization)
        else:
            raise ValueError("summarization=True 需要传入自定义实例（需要模型参数）")

    # ==========================================================================
    # [7] TodoMiddleware - 任务追踪（计划模式）
    # 类比：Redux DevTools 的 action logger，追踪任务执行流程
    # 只在 plan_mode=True 时启用，帮助 AI 管理多步骤任务
    # ==========================================================================
    if plan_mode:
        from deerflow.agents.middlewares.todo_middleware import TodoMiddleware

        chain.append(TodoMiddleware(
            system_prompt=_TODO_SYSTEM_PROMPT,
            tool_description=_TODO_TOOL_DESCRIPTION
        ))

    # ==========================================================================
    # [8] TitleMiddleware - 自动生成标题
    # 类比：根据内容自动生成文件名或文档标题
    # 首次对话后自动总结主题作为对话标题
    # ==========================================================================
    if feat.auto_title is not False:
        if isinstance(feat.auto_title, AgentMiddleware):
            chain.append(feat.auto_title)
        else:
            from deerflow.agents.middlewares.title_middleware import TitleMiddleware

            chain.append(TitleMiddleware())

    # ==========================================================================
    # [9] MemoryMiddleware - 记忆管理
    # 类比：Redux Persist 或 localStorage 同步器
    # 把用户偏好、重要信息持久化，下次对话时恢复
    # ==========================================================================
    if feat.memory is not False:
        if isinstance(feat.memory, AgentMiddleware):
            chain.append(feat.memory)
        else:
            from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware

            chain.append(MemoryMiddleware(agent_name=name))

    # ==========================================================================
    # [10] Vision Middleware - 视觉处理
    # 类比：图片上传组件的预览功能
    # 让 AI 能"看懂"上传的图片，自动提取图片信息
    # ==========================================================================
    if feat.vision is not False:
        if isinstance(feat.vision, AgentMiddleware):
            chain.append(feat.vision)
        else:
            from deerflow.agents.middlewares.view_image_middleware import ViewImageMiddleware

            chain.append(ViewImageMiddleware())
        from deerflow.tools.builtins import view_image_tool

        extra_tools.append(view_image_tool)

    # ==========================================================================
    # [11] Subagent Middleware - 子 Agent 管理
    # 类比：Promise.all 的并发控制器，限制同时执行的子任务数量
    # 防止 AI 一次启动太多子任务导致资源耗尽
    # ==========================================================================
    if feat.subagent is not False:
        if isinstance(feat.subagent, AgentMiddleware):
            chain.append(feat.subagent)
        else:
            from deerflow.agents.middlewares.subagent_limit_middleware import SubagentLimitMiddleware

            chain.append(SubagentLimitMiddleware())
        from deerflow.tools.builtins import task_tool

        extra_tools.append(task_tool)

    # ==========================================================================
    # [12] LoopDetectionMiddleware - 循环检测
    # 类比：React 的无限循环检测（如 useEffect 依赖项警告）
    # 检测 AI 是否陷入重复调用工具的循环，及时打断
    # ==========================================================================
    from deerflow.agents.middlewares.loop_detection_middleware import LoopDetectionMiddleware

    chain.append(LoopDetectionMiddleware())

    # ==========================================================================
    # [13] ClarificationMiddleware - 澄清请求处理（始终最后）
    # 类比：表单提交前的确认弹窗
    # 拦截需要用户确认的请求，确保重要操作得到确认
    # ==========================================================================
    chain.append(ClarificationMiddleware())
    extra_tools.append(ask_clarification_tool)

    # ==========================================================================
    # 插入额外中间件 - 使用 @Next/@Prev 定位
    # 类比：在 Express 中间件链中插入自定义中间件
    # 允许用户精确定位自定义中间件的位置
    # ==========================================================================
    if extra_middleware:
        _insert_extra(chain, extra_middleware)
        # 不变式：ClarificationMiddleware 必须始终在最后
        # @Next(ClarificationMiddleware) 可能会把它推离末尾，需要修正
        clar_idx = next(i for i, m in enumerate(chain) if isinstance(m, ClarificationMiddleware))
        if clar_idx != len(chain) - 1:
            chain.append(chain.pop(clar_idx))

    return chain, extra_tools


# ---------------------------------------------------------------------------
# Internal: extra middleware insertion with @Next/@Prev
# ---------------------------------------------------------------------------


def _insert_extra(chain: list[AgentMiddleware], extras: list[AgentMiddleware]) -> None:
    """Insert extra middlewares into *chain* using ``@Next``/``@Prev`` anchors.

    Algorithm:
      1. Validate: no middleware has both @Next and @Prev.
      2. Conflict detection: two extras targeting same anchor (same or opposite direction) → error.
      3. Insert unanchored extras before ClarificationMiddleware.
      4. Insert anchored extras iteratively (supports cross-external anchoring).
      5. If an anchor cannot be resolved after all rounds → error.
    """
    next_targets: dict[type, type] = {}
    prev_targets: dict[type, type] = {}

    anchored: list[tuple[AgentMiddleware, str, type]] = []
    unanchored: list[AgentMiddleware] = []

    for mw in extras:
        next_anchor = getattr(type(mw), "_next_anchor", None)
        prev_anchor = getattr(type(mw), "_prev_anchor", None)

        if next_anchor and prev_anchor:
            raise ValueError(f"{type(mw).__name__} cannot have both @Next and @Prev")

        if next_anchor:
            if next_anchor in next_targets:
                raise ValueError(f"Conflict: {type(mw).__name__} and {next_targets[next_anchor].__name__} both @Next({next_anchor.__name__})")
            if next_anchor in prev_targets:
                raise ValueError(f"Conflict: {type(mw).__name__} @Next({next_anchor.__name__}) and {prev_targets[next_anchor].__name__} @Prev({next_anchor.__name__}) — use cross-anchoring between extras instead")
            next_targets[next_anchor] = type(mw)
            anchored.append((mw, "next", next_anchor))
        elif prev_anchor:
            if prev_anchor in prev_targets:
                raise ValueError(f"Conflict: {type(mw).__name__} and {prev_targets[prev_anchor].__name__} both @Prev({prev_anchor.__name__})")
            if prev_anchor in next_targets:
                raise ValueError(f"Conflict: {type(mw).__name__} @Prev({prev_anchor.__name__}) and {next_targets[prev_anchor].__name__} @Next({prev_anchor.__name__}) — use cross-anchoring between extras instead")
            prev_targets[prev_anchor] = type(mw)
            anchored.append((mw, "prev", prev_anchor))
        else:
            unanchored.append(mw)

    # Unanchored → before ClarificationMiddleware
    clarification_idx = next(i for i, m in enumerate(chain) if isinstance(m, ClarificationMiddleware))
    for mw in unanchored:
        chain.insert(clarification_idx, mw)
        clarification_idx += 1

    # Anchored → iterative insertion (supports external-to-external anchoring)
    pending = list(anchored)
    max_rounds = len(pending) + 1
    for _ in range(max_rounds):
        if not pending:
            break
        remaining = []
        for mw, direction, anchor in pending:
            idx = next(
                (i for i, m in enumerate(chain) if isinstance(m, anchor)),
                None,
            )
            if idx is None:
                remaining.append((mw, direction, anchor))
                continue
            if direction == "next":
                chain.insert(idx + 1, mw)
            else:
                chain.insert(idx, mw)
        if len(remaining) == len(pending):
            names = [type(m).__name__ for m, _, _ in remaining]
            anchor_types = {a for _, _, a in remaining}
            remaining_types = {type(m) for m, _, _ in remaining}
            circular = anchor_types & remaining_types
            if circular:
                raise ValueError(f"Circular dependency among extra middlewares: {', '.join(t.__name__ for t in circular)}")
            raise ValueError(f"Cannot resolve positions for {', '.join(names)} — anchors {', '.join(a.__name__ for _, _, a in remaining)} not found in chain")
        pending = remaining
