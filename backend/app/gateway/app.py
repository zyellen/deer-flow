import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.gateway.config import get_gateway_config
from app.gateway.deps import langgraph_runtime
from app.gateway.routers import (
    agents,
    artifacts,
    assistants_compat,
    channels,
    mcp,
    memory,
    models,
    runs,
    skills,
    suggestions,
    thread_runs,
    threads,
    uploads,
)
from deerflow.config.app_config import get_app_config

# =============================================================================
# 日志配置 - 类似于前端 console.log 的全局配置
# 想象一下这是你在 React 应用的入口设置的日志级别
# =============================================================================
logging.basicConfig(
    level=logging.INFO,  # 日志级别：DEBUG < INFO < WARNING < ERROR
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 获取当前模块的 logger 实例
# 类似于 const logger = createLogger('gateway:app')
logger = logging.getLogger(__name__)


# =============================================================================
# 应用生命周期管理器 - 类似于 React 的 useEffect + cleanup 组合
#
# 比喻理解：
# - 这就像 React 组件的挂载和卸载生命周期
# - asynccontextmanager = useEffect(() => { setup(); return () => cleanup(); }, [])
# - yield 之前的代码 = 组件挂载时的初始化逻辑
# - yield 之后的代码 = 组件卸载时的清理逻辑
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期处理器 - 管理服务的启动和优雅关闭"""

    # -------------------------------------------------------------------------
    # 【启动阶段】= React 组件 Mount 时的初始化
    # 就像你的 App 组件启动时要检查 API 连接、初始化状态管理器
    # -------------------------------------------------------------------------
    try:
        # 加载全局配置 - 类似于读取 window.ENV 或 import.meta.env
        get_app_config()
        logger.info("配置加载成功 ✅")
    except Exception as e:
        # 启动失败就抛出异常阻止服务启动
        # 类似于 React 的 Error Boundary 捕获启动错误
        error_msg = f"网关启动时加载配置失败: {e}"
        logger.exception(error_msg)
        raise RuntimeError(error_msg) from e

    config = get_gateway_config()
    logger.info(f"API 网关启动中 {config.host}:{config.port} 🚀")

    # -------------------------------------------------------------------------
    # 初始化 LangGraph 运行时
    # 比喻：这就像是初始化 React Context，让整个应用树都能访问共享状态
    # async with = React 的 Suspense，等待异步初始化完成
    # -------------------------------------------------------------------------
    async with langgraph_runtime(app):
        logger.info("LangGraph 运行时初始化完成 ⚡")

        # 启动 IM 渠道服务（飞书/Slack/钉钉等集成）
        # 类似于初始化 WebSocket 连接或第三方 SDK
        try:
            from app.channels.service import start_channel_service

            channel_service = await start_channel_service()
            logger.info("IM 渠道服务启动: %s", channel_service.get_status())
        except Exception:
            # 渠道服务失败不会阻止主服务启动，只是记录日志
            logger.exception("IM 渠道未配置或服务启动失败（非致命）")

        # yield = 服务正式启动，开始接受请求
        # 就像 React 中 return 之后的渲染，表示初始化完成
        yield

        # ---------------------------------------------------------------------
        # 【关闭阶段】= React 组件 Unmount 时的清理
        # 就像 useEffect 的 cleanup 函数，关闭连接、清理资源
        # ---------------------------------------------------------------------
        try:
            from app.channels.service import stop_channel_service

            await stop_channel_service()
            logger.info("IM 渠道服务已关闭")
        except Exception:
            logger.exception("关闭渠道服务时出错")

    logger.info("API 网关已关闭 👋")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    比喻理解：
    - 这就像创建一个 React 应用的根组件
    - FastAPI = React Application Shell
    - router = 路由配置 (react-router-dom 的 Routes)
    - middleware = 全局拦截器/中间件

    Returns:
        配置好的 FastAPI 应用实例
    """

    # =============================================================================
    # 创建 FastAPI 应用实例
    # 类似于：const app = createApp({ ... })
    # =============================================================================
    app = FastAPI(
        title="DeerFlow API Gateway",
        description="""
## DeerFlow API Gateway - 用前端思维理解

API 网关是 DeerFlow 的"入口组件"，基于 LangGraph 构建 AI Agent 后端。

### 类比 React 架构理解：

```
DeerFlow 架构 ≈ 现代 React 应用
├── API Gateway (本文件) = App Router + API Routes
├── LangGraph = React 状态管理 (Redux/Zustand) + 工作流引擎
├── Agents = 智能组件，能自主决定调用什么工具
├── Tools = API Client 函数，调用外部服务
└── Middlewares = 请求拦截器 (axios interceptors)
```

### 核心功能模块：

| 模块 | 类比前端概念 | 作用 |
|------|-------------|------|
| Models | 组件库选择器 | 管理可用的 AI 模型 |
| MCP | 第三方服务配置 | 管理外部工具服务连接 |
| Memory | localStorage / Redux Persist | 持久化用户记忆 |
| Skills | npm 包管理 | 动态加载功能模块 |
| Artifacts | 文件下载服务 | 生成的文件资源 |

### 请求流向：

```
用户请求 → nginx (反向代理) → API Gateway → LangGraph Agent → 响应
                ↓
        静态资源服务 (类比 CDN)
```
        """,
        version="0.1.0",
        lifespan=lifespan,  # 传入生命周期管理器
        docs_url="/docs",   # API 文档地址 (类似 Storybook)
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=[
            {
                "name": "models",
                "description": "Operations for querying available AI models and their configurations",
            },
            {
                "name": "mcp",
                "description": "Manage Model Context Protocol (MCP) server configurations",
            },
            {
                "name": "memory",
                "description": "Access and manage global memory data for personalized conversations",
            },
            {
                "name": "skills",
                "description": "Manage skills and their configurations",
            },
            {
                "name": "artifacts",
                "description": "Access and download thread artifacts and generated files",
            },
            {
                "name": "uploads",
                "description": "Upload and manage user files for threads",
            },
            {
                "name": "threads",
                "description": "Manage DeerFlow thread-local filesystem data",
            },
            {
                "name": "agents",
                "description": "Create and manage custom agents with per-agent config and prompts",
            },
            {
                "name": "suggestions",
                "description": "Generate follow-up question suggestions for conversations",
            },
            {
                "name": "channels",
                "description": "Manage IM channel integrations (Feishu, Slack, Telegram)",
            },
            {
                "name": "assistants-compat",
                "description": "LangGraph Platform-compatible assistants API (stub)",
            },
            {
                "name": "runs",
                "description": "LangGraph Platform-compatible runs lifecycle (create, stream, cancel)",
            },
            {
                "name": "health",
                "description": "Health check and system status endpoints",
            },
        ],
    )

    # ==========================================================================
    # CORS 处理说明
    # 类似于前端配置 axios.defaults.withCredentials
    # 这里由 nginx 统一处理跨域，Gateway 不需要额外配置
    # ==========================================================================

    # ==========================================================================
    # 注册路由模块 - 类似于 react-router-dom 的 <Route /> 配置
    #
    # 每个 router 都是一个 Blueprint（蓝图），包含一组相关接口
    # 类比前端：每个 router 就像一个 feature 模块的 API 集合
    # ==========================================================================

    # --------------------------------------------------------------------------
    # Models 路由 - AI 模型管理
    # 类比：获取可用的 UI 组件列表，比如 <GPT4 /> <Claude /> 等
    # GET /api/models - 获取所有可用模型
    # --------------------------------------------------------------------------
    app.include_router(models.router)

    # --------------------------------------------------------------------------
    # MCP 路由 - Model Context Protocol 配置管理
    # 类比：管理第三方服务集成配置（类似管理 API Keys）
    # MCP 让 AI 能调用外部工具，就像你的组件调用第三方 SDK
    # --------------------------------------------------------------------------
    app.include_router(mcp.router)

    # --------------------------------------------------------------------------
    # Memory 路由 - 全局记忆管理
    # 类比：用户偏好设置的 CRUD API（像 localStorage 的服务器版）
    # 让 AI 记住用户的信息，提供个性化回复
    # --------------------------------------------------------------------------
    app.include_router(memory.router)

    # --------------------------------------------------------------------------
    # Skills 路由 - 技能管理
    # 类比：npm 包管理，动态安装/卸载功能模块
    # 每个 skill 就像一个可插拔的 React Hook
    # --------------------------------------------------------------------------
    app.include_router(skills.router)

    # --------------------------------------------------------------------------
    # Artifacts 路由 - 生成文件资源管理
    # 类比：文件下载服务，用户生成的图片、代码、文档等
    # 路径：/api/threads/{thread_id}/artifacts
    # --------------------------------------------------------------------------
    app.include_router(artifacts.router)

    # --------------------------------------------------------------------------
    # Uploads 路由 - 文件上传管理
    # 类比：FormData 文件上传接口，处理用户上传的图片/文档
    # 路径：/api/threads/{thread_id}/uploads
    # --------------------------------------------------------------------------
    app.include_router(uploads.router)

    # --------------------------------------------------------------------------
    # Threads 路由 - 对话线程管理
    # 类比：聊天记录的 CRUD，创建/删除/清理对话会话
    # --------------------------------------------------------------------------
    app.include_router(threads.router)

    # --------------------------------------------------------------------------
    # Agents 路由 - 自定义 Agent 管理
    # 类比：自定义组件配置，用户可以创建专属 AI 助手
    # 每个 Agent 就像一个配置好的智能组件
    # --------------------------------------------------------------------------
    app.include_router(agents.router)

    # --------------------------------------------------------------------------
    # Suggestions 路由 - 后续问题建议生成
    # 类比：搜索框的自动补全或相关推荐
    # 根据对话内容生成用户可能想问的问题
    # --------------------------------------------------------------------------
    app.include_router(suggestions.router)

    # --------------------------------------------------------------------------
    # Channels 路由 - IM 渠道集成管理
    # 类比：多平台登录集成（飞书、Slack、Telegram Bot）
    # 让 AI 助手能在多个平台回复消息
    # --------------------------------------------------------------------------
    app.include_router(channels.router)

    # --------------------------------------------------------------------------
    # 以下是为了兼容 LangGraph Platform 的 API 设计
    # 类比：为了保持向后兼容的 legacy API
    # --------------------------------------------------------------------------
    app.include_router(assistants_compat.router)  # LangGraph Platform 兼容层
    app.include_router(thread_runs.router)        # 对话运行生命周期管理
    app.include_router(runs.router)               # 无状态运行接口（流式响应）

    # ==========================================================================
    # 健康检查端点 - 类似于前端的心beat 检测
    # 用于负载均衡器判断服务是否可用
    # 类比：React DevTools 的组件状态指示器
    # ==========================================================================
    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """健康检查端点。

        返回：
            服务健康状态信息，类似于 { status: 'ok', uptime: 1234 }

        使用场景：
        - Docker/K8s 健康探针
        - 负载均衡器健康检查
        - 监控系统的存活检测
        """
        return {"status": "healthy", "service": "deer-flow-gateway"}

    return app


# =============================================================================
# 创建应用实例 - 供 uvicorn 服务器启动使用
# 类似于：export const app = createApp();
#
# 启动命令：uvicorn app.gateway.app:app --reload
# 这告诉 uvicorn：从 app.gateway.app 模块导入 app 变量
# =============================================================================
app = create_app()
