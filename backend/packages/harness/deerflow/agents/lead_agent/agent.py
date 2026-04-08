"""
Lead Agent（主 Agent）创建模块 - 用前端思维理解

这个模块就像是创建一个"智能组件工厂"，专门生产具备完整功能的 AI 助手。

【核心比喻】
想象一下你在构建一个智能客服组件：

```typescript
function LeadAgent({
  model,              // 选择 AI 模型（像选 GPT-4 还是 Claude）
  tools,              // 可用工具集（查询订单、修改密码等 API）
  systemPrompt,       // 角色设定（"你是专业客服，语气要友好"）
  middlewares,        // 拦截器链（日志、限流、缓存等）
  enableMemory,       // 是否记住用户偏好
  enableVision,       // 是否支持看图
}) {
  // 1. 创建模型实例
  // 2. 组装中间件管道
  // 3. 生成系统提示词
  // 4. 返回可运行的 Agent
}
```

【架构层次】（从下往上）

1. LangChain create_agent = React.createElement（最底层）
2. create_deerflow_agent = 高阶组件（HOC），可复用的基础包装
3. make_lead_agent = 业务级组件，带完整业务配置（本文件）

就像：
- createElement → 基础函数
- withRouter(withStyles(Component)) → HOC 链
- <App /> → 完整的业务组件
"""

import logging

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain_core.runnables import RunnableConfig

from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.middlewares.clarification_middleware import ClarificationMiddleware
from deerflow.agents.middlewares.loop_detection_middleware import LoopDetectionMiddleware
from deerflow.agents.middlewares.memory_middleware import MemoryMiddleware
from deerflow.agents.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
from deerflow.agents.middlewares.title_middleware import TitleMiddleware
from deerflow.agents.middlewares.todo_middleware import TodoMiddleware
from deerflow.agents.middlewares.token_usage_middleware import TokenUsageMiddleware
from deerflow.agents.middlewares.tool_error_handling_middleware import build_lead_runtime_middlewares
from deerflow.agents.middlewares.view_image_middleware import ViewImageMiddleware
from deerflow.agents.thread_state import ThreadState
from deerflow.config.agents_config import load_agent_config
from deerflow.config.app_config import get_app_config
from deerflow.config.summarization_config import get_summarization_config
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)


def _resolve_model_name(requested_model_name: str | None = None) -> str:
    """
    模型名称解析器 - 安全地确定使用哪个 AI 模型

    类比前端：这就像一个 "API endpoint 选择器"：
    1. 用户指定了就用用户指定的
    2. 用户没指定或指定无效，就用默认的
    3. 都没有配置就报错

    类似于：
    ```typescript
    function resolveApiEndpoint(requestedEndpoint?: string): string {
      const defaultEndpoint = config.endpoints[0];
      if (!defaultEndpoint) throw new Error('没有配置 API 端点');
      if (requestedEndpoint && isValid(requestedEndpoint)) {
        return requestedEndpoint;
      }
      return defaultEndpoint;
    }
    ```
    """
    app_config = get_app_config()
    default_model_name = app_config.models[0].name if app_config.models else None
    if default_model_name is None:
        raise ValueError("没有配置聊天模型，请在 config.yaml 中至少配置一个模型")

    # 用户请求的模型有效就用用户的
    if requested_model_name and app_config.get_model_config(requested_model_name):
        return requested_model_name

    # 用户请求的模型无效，回退到默认并警告
    if requested_model_name and requested_model_name != default_model_name:
        logger.warning(f"模型 '{requested_model_name}' 未找到，回退到默认模型 '{default_model_name}'")
    return default_model_name


def _create_summarization_middleware() -> SummarizationMiddleware | None:
    """
    创建摘要中间件 - 长对话的"虚拟滚动"功能

    【核心比喻】
    这就像前端长列表的虚拟滚动（Virtual Scrolling）：
    - 当对话历史太长时，自动把旧消息"摘要化"
    - 保留最近 N 条完整消息（像保留视口内的项目）
    - 旧消息变成摘要形式（像列表项变成占位符）

    类比 React Virtual List：
    ```typescript
    function VirtualMessageList({ messages }) {
      // 当消息超过 1000 条，把最早的 800 条摘要成一句话
      const displayMessages = messages.length > 1000
        ? [summaryOfFirst800, ...messages.slice(-200)]
        : messages;
    }
    ```

    【配置参数】
    - enabled: 是否开启虚拟滚动
    - trigger: 触发条件（如消息数超过 N，或 token 数超过 M）
    - keep: 保留多少条最近消息不摘要
    - model: 用什么模型做摘要（通常用轻量级模型节省成本）
    """
    config = get_summarization_config()

    if not config.enabled:
        return None

    # 准备触发条件参数
    trigger = None
    if config.trigger is not None:
        if isinstance(config.trigger, list):
            trigger = [t.to_tuple() for t in config.trigger]
        else:
            trigger = config.trigger.to_tuple()

    # 准备保留策略
    keep = config.keep.to_tuple()

    # 准备模型参数
    if config.model_name:
        model = create_chat_model(name=config.model_name, thinking_enabled=False)
    else:
        # 摘要任务用轻量级模型，节省成本
        # 就像列表滚动不需要重新渲染全部内容
        model = create_chat_model(thinking_enabled=False)

    # 组装参数
    kwargs = {
        "model": model,
        "trigger": trigger,
        "keep": keep,
    }

    if config.trim_tokens_to_summarize is not None:
        kwargs["trim_tokens_to_summarize"] = config.trim_tokens_to_summarize

    if config.summary_prompt is not None:
        kwargs["summary_prompt"] = config.summary_prompt

    return SummarizationMiddleware(**kwargs)


def _create_todo_list_middleware(is_plan_mode: bool) -> TodoMiddleware | None:
    """Create and configure the TodoList middleware.

    Args:
        is_plan_mode: Whether to enable plan mode with TodoList middleware.

    Returns:
        TodoMiddleware instance if plan mode is enabled, None otherwise.
    """
    if not is_plan_mode:
        return None

    # Custom prompts matching DeerFlow's style
    system_prompt = """
<todo_list_system>
You have access to the `write_todos` tool to help you manage and track complex multi-step objectives.

**CRITICAL RULES:**
- Mark todos as completed IMMEDIATELY after finishing each step - do NOT batch completions
- Keep EXACTLY ONE task as `in_progress` at any time (unless tasks can run in parallel)
- Update the todo list in REAL-TIME as you work - this gives users visibility into your progress
- DO NOT use this tool for simple tasks (< 3 steps) - just complete them directly

**When to Use:**
This tool is designed for complex objectives that require systematic tracking:
- Complex multi-step tasks requiring 3+ distinct steps
- Non-trivial tasks needing careful planning and execution
- User explicitly requests a todo list
- User provides multiple tasks (numbered or comma-separated list)
- The plan may need revisions based on intermediate results

**When NOT to Use:**
- Single, straightforward tasks
- Trivial tasks (< 3 steps)
- Purely conversational or informational requests
- Simple tool calls where the approach is obvious

**Best Practices:**
- Break down complex tasks into smaller, actionable steps
- Use clear, descriptive task names
- Remove tasks that become irrelevant
- Add new tasks discovered during implementation
- Don't be afraid to revise the todo list as you learn more

**Task Management:**
Writing todos takes time and tokens - use it when helpful for managing complex problems, not for simple requests.
</todo_list_system>
"""

    tool_description = """Use this tool to create and manage a structured task list for complex work sessions.

**IMPORTANT: Only use this tool for complex tasks (3+ steps). For simple requests, just do the work directly.**

## When to Use

Use this tool in these scenarios:
1. **Complex multi-step tasks**: When a task requires 3 or more distinct steps or actions
2. **Non-trivial tasks**: Tasks requiring careful planning or multiple operations
3. **User explicitly requests todo list**: When the user directly asks you to track tasks
4. **Multiple tasks**: When users provide a list of things to be done
5. **Dynamic planning**: When the plan may need updates based on intermediate results

## When NOT to Use

Skip this tool when:
1. The task is straightforward and takes less than 3 steps
2. The task is trivial and tracking provides no benefit
3. The task is purely conversational or informational
4. It's clear what needs to be done and you can just do it

## How to Use

1. **Starting a task**: Mark it as `in_progress` BEFORE beginning work
2. **Completing a task**: Mark it as `completed` IMMEDIATELY after finishing
3. **Updating the list**: Add new tasks, remove irrelevant ones, or update descriptions as needed
4. **Multiple updates**: You can make several updates at once (e.g., complete one task and start the next)

## Task States

- `pending`: Task not yet started
- `in_progress`: Currently working on (can have multiple if tasks run in parallel)
- `completed`: Task finished successfully

## Task Completion Requirements

**CRITICAL: Only mark a task as completed when you have FULLY accomplished it.**

Never mark a task as completed if:
- There are unresolved issues or errors
- Work is partial or incomplete
- You encountered blockers preventing completion
- You couldn't find necessary resources or dependencies
- Quality standards haven't been met

If blocked, keep the task as `in_progress` and create a new task describing what needs to be resolved.

## Best Practices

- Create specific, actionable items
- Break complex tasks into smaller, manageable steps
- Use clear, descriptive task names
- Update task status in real-time as you work
- Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
- Remove tasks that are no longer relevant
- **IMPORTANT**: When you write the todo list, mark your first task(s) as `in_progress` immediately
- **IMPORTANT**: Unless all tasks are completed, always have at least one task `in_progress` to show progress

Being proactive with task management demonstrates thoroughness and ensures all requirements are completed successfully.

**Remember**: If you only need a few tool calls to complete a task and it's clear what to do, it's better to just do the task directly and NOT use this tool at all.
"""

    return TodoMiddleware(system_prompt=system_prompt, tool_description=tool_description)


def _build_middlewares(config: RunnableConfig, model_name: str | None, agent_name: str | None = None, custom_middlewares: list[AgentMiddleware] | None = None):
    """
    构建中间件链 - 组装 AI 助手的"处理管道"

    【比喻：Express/Koa 中间件栈】
    请求流向就像数据流过管道：
    ```
    用户输入 → ThreadData → Uploads → Sandbox → DanglingToolCall
                ↓
              Guardrail → ErrorHandler → Summarization → TodoList
                ↓
              Title → Memory → Vision → DeferredFilter → Subagent
                ↓
              LoopDetection → Custom → Clarification → AI Agent
    ```

    【中间件顺序的重要性】
    就像 Redux middleware 的顺序会影响行为：

    1. ThreadDataMiddleware (最先)
       - 初始化线程上下文（类似创建 React Context）
       - 必须在 Sandbox 之前，因为沙盒需要 thread_id

    2. UploadsMiddleware
       - 处理文件上传（类似 multer 中间件）
       - 依赖 ThreadData 提供的 thread_id

    3. DanglingToolCallMiddleware
       - 修复中断的工具调用（类似处理 pending Promise）
       - 必须在 AI 看到历史之前处理

    4. SummarizationMiddleware
       - 长对话摘要（类似虚拟滚动）
       - 尽早处理可以减少后续中间件的工作量

    5. TodoListMiddleware
       - 任务追踪（像 Redux DevTools）
       - 要在 Clarification 之前，让 AI 能管理任务

    6. TitleMiddleware
       - 自动生成标题（像自动生成文件名）
       - 在首次对话后触发

    7. MemoryMiddleware
       - 记忆持久化（像 Redux Persist）
       - 在 Title 之后，确保标题被记住

    8. ViewImageMiddleware
       - 图片处理（像上传预览）
       - 在 Clarification 之前注入图片描述

    9. ToolErrorHandlingMiddleware
       - 错误转换（像 axios error interceptor）
       - 在 Clarification 之前把异常转为消息

    10. ClarificationMiddleware (内置最后)
        - 确认拦截（像确认弹窗）
        - 始终最后，拦截所有需要用户确认的请求

    Args:
        config: 运行时配置（包含 is_plan_mode 等选项）
        model_name: 模型名称，Vision 中间件需要检查是否支持图片
        agent_name: Agent 名称，Memory 用做命名空间
        custom_middlewares: 自定义中间件列表（可选）

    Returns:
        中间件实例列表（有序的）
    """
    # ==========================================================================
    # 第一阶段：构建基础运行时中间件（Sandbox 基础设施）
    # 类比：Express 应用的基础中间件（body-parser、cookie-parser 等）
    # ==========================================================================
    middlewares = build_lead_runtime_middlewares(lazy_init=True)

    # ==========================================================================
    # 第二阶段：根据配置动态添加功能中间件
    # 类比：根据 feature flags 动态启用 Redux middleware
    # ==========================================================================

    # 摘要中间件 - 长对话自动摘要（虚拟滚动）
    summarization_middleware = _create_summarization_middleware()
    if summarization_middleware is not None:
        middlewares.append(summarization_middleware)

    # 计划模式中间件 - 任务追踪器
    is_plan_mode = config.get("configurable", {}).get("is_plan_mode", False)
    todo_list_middleware = _create_todo_list_middleware(is_plan_mode)
    if todo_list_middleware is not None:
        middlewares.append(todo_list_middleware)

    # Token 用量追踪 - 像性能监控中间件
    if get_app_config().token_usage.enabled:
        middlewares.append(TokenUsageMiddleware())

    # 自动标题生成 - 像自动生成页面标题
    middlewares.append(TitleMiddleware())

    # 记忆中间件 - 像 Redux Persist，持久化用户偏好
    # 放在 Title 之后，让标题也能被记住
    middlewares.append(MemoryMiddleware(agent_name=agent_name))

    # 视觉中间件 - 仅当模型支持图片时启用
    # 就像根据浏览器特性启用功能
    app_config = get_app_config()
    model_config = app_config.get_model_config(model_name) if model_name else None
    if model_config is not None and model_config.supports_vision:
        middlewares.append(ViewImageMiddleware())

    # 延迟工具过滤器 - 从模型绑定中隐藏延迟工具模式
    # 像 API 路由过滤中间件
    if app_config.tool_search.enabled:
        from deerflow.agents.middlewares.deferred_tool_filter_middleware import DeferredToolFilterMiddleware

        middlewares.append(DeferredToolFilterMiddleware())

    # 子 Agent 限制器 - 并发控制（像 p-limit）
    subagent_enabled = config.get("configurable", {}).get("subagent_enabled", False)
    if subagent_enabled:
        max_concurrent_subagents = config.get("configurable", {}).get("max_concurrent_subagents", 3)
        middlewares.append(SubagentLimitMiddleware(max_concurrent=max_concurrent_subagents))

    # 循环检测中间件 - 像 React 的无限循环警告
    middlewares.append(LoopDetectionMiddleware())

    # ==========================================================================
    # 第三阶段：插入用户自定义中间件
    # 类比：应用级别的自定义 Express middleware
    # ==========================================================================
    if custom_middlewares:
        middlewares.extend(custom_middlewares)

    # ==========================================================================
    # 最后：确认中间件（始终最后）
    # 像全局的请求确认拦截器
    # ==========================================================================
    middlewares.append(ClarificationMiddleware())
    return middlewares


def make_lead_agent(config: RunnableConfig):
    """
    创建主 Agent（Lead Agent）- 业务级 Agent 工厂

    【核心比喻】
    这就像根据用户配置创建一个完整的"智能客服组件"：

    ```typescript
    function createLeadAgent(runtimeConfig) {
      // 1. 解析配置（像处理组件 props）
      const {
        modelName,         // 选择 AI 模型
        thinkingEnabled,   // 是否开启深度思考
        planMode,          // 是否启用任务追踪
        subagentEnabled,   // 是否允许子任务
      } = runtimeConfig;

      // 2. 加载 Agent 配置（像读取组件预设）
      const agentConfig = loadAgentConfig(agentName);

      // 3. 创建模型实例（像初始化 API 客户端）
      const model = createChatModel({ name: modelName, thinkingEnabled });

      // 4. 获取可用工具集（像导入 API 函数）
      const tools = getAvailableTools({ modelName, groups: agentConfig.toolGroups });

      // 5. 组装中间件链（像配置 Redux middleware）
      const middlewares = buildMiddlewares(config, modelName, agentName);

      // 6. 生成系统提示词（像组件的默认 props）
      const systemPrompt = applyPromptTemplate({ ... });

      // 7. 创建并返回 Agent 实例
      return createAgent({ model, tools, middlewares, systemPrompt });
    }
    ```

    【配置优先级】（从高到低）
    1. 运行时请求参数（用户当前选择）
    2. Agent 自定义配置（该 Agent 的专属配置）
    3. 全局默认配置（系统默认值）

    就像 React 组件的 props 优先级：
    runtimeProps > componentDefaultProps > globalConfig
    """
    # 延迟导入避免循环依赖
    # 类似于动态 import()，避免启动时加载所有模块
    from deerflow.tools import get_available_tools
    from deerflow.tools.builtins import setup_agent

    # ==========================================================================
    # 解析运行时配置
    # 从 config.configurable 中提取用户传入的参数
    # 类似于从函数参数或 URL query string 中提取配置
    # ==========================================================================
    cfg = config.get("configurable", {})

    # 核心功能开关
    thinking_enabled = cfg.get("thinking_enabled", True)        # 是否启用深度思考
    reasoning_effort = cfg.get("reasoning_effort", None)        # 推理努力程度（低/中/高）
    requested_model_name: str | None = cfg.get("model_name") or cfg.get("model")  # 请求的模型
    is_plan_mode = cfg.get("is_plan_mode", False)               # 是否启用计划模式
    subagent_enabled = cfg.get("subagent_enabled", False)       # 是否启用子 Agent
    max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)  # 最大并发子任务数
    is_bootstrap = cfg.get("is_bootstrap", False)               # 是否为引导模式
    agent_name = cfg.get("agent_name")                          # Agent 名称（自定义 Agent 用）

    # ==========================================================================
    # 加载 Agent 配置
    # 如果指定了 agent_name，加载该 Agent 的专属配置
    # 类似于读取组件的配置文件或 preset
    # ==========================================================================
    agent_config = load_agent_config(agent_name) if not is_bootstrap else None

    # 确定最终使用的模型名称（优先级：请求 > Agent配置 > 全局默认）
    agent_model_name = agent_config.model if agent_config and agent_config.model else _resolve_model_name()
    model_name = requested_model_name or agent_model_name

    # 获取模型配置
    app_config = get_app_config()
    model_config = app_config.get_model_config(model_name) if model_name else None

    # 验证模型配置
    if model_config is None:
        raise ValueError("无法解析聊天模型配置，请在 config.yaml 中配置模型或提供有效的 model_name")

    # 检查模型是否支持思考模式
    if thinking_enabled and not model_config.supports_thinking:
        logger.warning(f"模型 '{model_name}' 不支持思考模式，回退到普通模式")
        thinking_enabled = False

    # 记录创建日志（像 React 的 props 检查日志）
    logger.info(
        "创建 Agent(%s) -> 思考模式: %s, 推理强度: %s, 模型: %s, 计划模式: %s, 子Agent: %s, 最大并发: %s",
        agent_name or "default",
        thinking_enabled,
        reasoning_effort,
        model_name,
        is_plan_mode,
        subagent_enabled,
        max_concurrent_subagents,
    )

    # ==========================================================================
    # 注入运行元数据（用于 LangSmith 追踪）
    # 类似于给 React 组件添加 data-testid 或 devtools 标记
    # ==========================================================================
    if "metadata" not in config:
        config["metadata"] = {}

    config["metadata"].update({
        "agent_name": agent_name or "default",
        "model_name": model_name or "default",
        "thinking_enabled": thinking_enabled,
        "reasoning_effort": reasoning_effort,
        "is_plan_mode": is_plan_mode,
        "subagent_enabled": subagent_enabled,
    })

    # ==========================================================================
    # 引导模式：最小化配置的引导 Agent
    # 用于首次创建自定义 Agent 的流程
    # 类比：应用初始化向导，只提供最基础的功能
    # ==========================================================================
    if is_bootstrap:
        return create_agent(
            model=create_chat_model(name=model_name, thinking_enabled=thinking_enabled),
            tools=get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled) + [setup_agent],
            middleware=_build_middlewares(config, model_name=model_name),
            system_prompt=apply_prompt_template(
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
                available_skills=set(["bootstrap"])
            ),
            state_schema=ThreadState,
        )

    # ==========================================================================
    # 默认主 Agent：完整功能配置
    # 这就像创建一个配置完备的智能组件
    # ==========================================================================
    return create_agent(
        model=create_chat_model(
            name=model_name,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort
        ),
        tools=get_available_tools(
            model_name=model_name,
            groups=agent_config.tool_groups if agent_config else None,
            subagent_enabled=subagent_enabled
        ),
        middleware=_build_middlewares(config, model_name=model_name, agent_name=agent_name),
        system_prompt=apply_prompt_template(
            subagent_enabled=subagent_enabled,
            max_concurrent_subagents=max_concurrent_subagents,
            agent_name=agent_name,
            available_skills=set(agent_config.skills) if agent_config and agent_config.skills is not None else None
        ),
        state_schema=ThreadState,
    )
