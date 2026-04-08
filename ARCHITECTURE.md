# DeerFlow 架构与运行流程图解

> 用前端思维理解 AI Agent 工作流平台（React + Vue 双版本类比）

## 一、整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户层 (User Layer)                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│  │   Web App   │  │  Feishu Bot │  │  Slack Bot  │  ... 其他 IM 渠道       │
│  │  (Next.js)  │  │             │  │             │                         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
│         │                │                │                                  │
│         └────────────────┴────────────────┘                                  │
│                          │                                                   │
└──────────────────────────┼───────────────────────────────────────────────────┘
                           │ HTTP / WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           网关层 (Gateway Layer)                             │
│                         nginx + FastAPI Gateway                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       ││
│  │  │/api/models  │ │  /api/mcp   │ │ /api/skills │ │/api/threads │ ...   ││
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       ││
│  │         └─────────────────┴─────────────────┴─────────────────┘         ││
│  │                             │                                           ││
│  │                    ┌────────▼────────┐                                  ││
│  │                    │  Router Dispatcher │  ← 路由分发                   ││
│  │                    └────────┬────────┘                                  ││
│  └─────────────────────────────┼───────────────────────────────────────────┘│
└────────────────────────────────┼────────────────────────────────────────────┘
                                 │ LangGraph Protocol
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          智能体层 (Agent Layer)                              │
│                           LangGraph Runtime                                  │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Agent 创建流程（工厂模式）                        │   │
│   │                                                                     │   │
│   │   用户请求 ──▶ make_lead_agent() ──▶ create_deerflow_agent()       │   │
│   │                              │                    │                 │   │
│   │                              ▼                    ▼                 │   │
│   │                    ┌─────────────────┐    ┌──────────────┐         │   │
│   │                    │  1. 加载 Agent 配置  │    │ 2. 组装中间件链 │         │   │
│   │                    │  (技能/工具/模型)   │    │  (14个中间件)  │         │   │
│   │                    └────────┬────────┘    └──────┬───────┘         │   │
│   │                             │                    │                 │   │
│   │                             └────────┬───────────┘                 │   │
│   │                                      ▼                             │   │
│   │                    ┌─────────────────────────────────┐             │   │
│   │                    │      3. 创建 Chat Model         │             │   │
│   │                    │   (GPT-4 / Claude / DeepSeek)   │             │   │
│   │                    └─────────────────────────────────┘             │   │
│   │                                      │                             │   │
│   │                                      ▼                             │   │
│   │                    ┌─────────────────────────────────┐             │   │
│   │                    │      4. 生成 System Prompt      │             │   │
│   │                    │   (角色设定 + 工具描述)          │             │   │
│   │                    └─────────────────────────────────┘             │   │
│   │                                      │                             │   │
│   │                                      ▼                             │   │
│   │                    ┌─────────────────────────────────┐             │   │
│   │                    │   5. 返回 CompiledStateGraph    │             │   │
│   │                    │      (可执行的 Agent 实例)       │             │   │
│   │                    └─────────────────────────────────┘             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 二、请求处理流程图

### 2.1 单次对话完整流程

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  用户   │────▶│ Frontend │────▶│ Gateway  │────▶│  Agent   │
└─────────┘     └──────────┘     └──────────┘     └────┬─────┘
                                                       │
                                                       ▼
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  用户   │◀────│ Frontend │◀────│ Gateway  │◀────│ Middleware│
└─────────┘     └──────────┘     └──────────┘     └────┬─────┘
                                                       │
                                                       ▼
                                              ┌────────────────┐
                                              │   LLM Model    │
                                              │ (GPT-4/Claude) │
                                              └───────┬────────┘
                                                      │
                              ┌───────────────────────┼───────────────────────┐
                              │                       │                       │
                              ▼                       ▼                       ▼
                        ┌──────────┐          ┌──────────┐          ┌──────────┐
                        │  Tools   │          │ Sandbox  │          │   DB     │
                        │ (Skills) │          │(代码执行) │          │(状态保存) │
                        └──────────┘          └──────────┘          └──────────┘
```

### 2.2 详细流程步骤

```
用户输入消息
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Frontend (Next.js / Vue)                                  │
│    - 捕获用户输入                                            │
│    - 构建请求体 {message, thread_id, model_name}            │
│    - 发送 POST /api/runs/stream                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Gateway (FastAPI)                                         │
│    - 验证请求参数                                            │
│    - 解析 model_name / agent_name                           │
│    - 路由到对应处理器                                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Agent 初始化                                              │
│    make_lead_agent(config)                                   │
│    ├── _resolve_model_name()  → 确定使用哪个 AI 模型        │
│    ├── _build_middlewares()   → 组装 14 个中间件            │
│    ├── create_chat_model()    → 创建模型实例                │
│    └── apply_prompt_template() → 生成系统提示词             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 中间件预处理（按顺序执行）                                 │
│    [0] ThreadDataMiddleware      → 初始化线程上下文         │
│    [1] UploadsMiddleware         → 处理文件上传             │
│    [2] SandboxMiddleware         → 准备沙盒环境             │
│    [3] DanglingToolCallMiddleware → 修复中断状态            │
│    [4] SummarizationMiddleware   → 长对话摘要               │
│    [5] TodoMiddleware            → 任务追踪(plan_mode)      │
│    [6] MemoryMiddleware          → 加载用户记忆             │
│    ... 更多中间件                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. LLM 推理循环                                              │
│    while True:                                               │
│        - 构建消息历史                                        │
│        - 调用 Chat Model                                     │
│        - 解析响应                                            │
│        - if 需要调用工具: 执行工具并继续循环                  │
│        - else: 返回最终响应                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. 工具执行（可选）                                          │
│    - 解析 tool_calls                                        │
│    - 路由到对应工具                                          │
│    - 代码工具 → 提交到 Sandbox 执行                         │
│    - 返回 ToolMessage 给 LLM                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. 中间件后处理（反向执行）                                   │
│    - MemoryMiddleware   → 保存新记忆                        │
│    - TitleMiddleware    → 生成/更新对话标题                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. 响应返回                                                  │
│    - SSE 流式传输到 Frontend                                │
│    - 前端实时显示 AI 回复                                   │
│    - 保存 checkpoint 到数据库                               │
└─────────────────────────────────────────────────────────────┘
```

## 三、Vue vs React 类比

### 3.1 核心概念对照表

| DeerFlow 概念 | React 类比 | Vue 类比 | 说明 |
|--------------|-----------|---------|------|
| **Agent** | React Component | Vue Component | 可复用的智能单元 |
| **StateGraph** | useReducer + Context | Pinia Store / Vuex | 状态管理 |
| **Middleware** | Redux Middleware | Pinia Plugins | 请求拦截处理链 |
| **Checkpointer** | Redux Persist | Pinia PersistedState | 状态持久化 |
| **Thread** | React Router Route | Vue Router Route | 独立对话会话 |
| **Factory Pattern** | HOC (高阶组件) | Composables | 组件工厂 |
| **Lifespan** | useEffect + cleanup | onMounted + onUnmounted | 生命周期管理 |
| **Context** | React Context | Provide / Inject | 依赖注入 |
| **Props** | Props | Props / Emits | 组件传参 |
| **Slots** | children | slots | 内容分发 |

### 3.2 代码对比示例

#### Agent 创建（工厂模式）

**React 风格思维：**
```typescript
// 就像创建高阶组件
function createSmartAgent({ model, tools, middlewares }) {
  return function AgentComponent(props) {
    // 使用 useReducer 管理状态
    const [state, dispatch] = useReducer(agentReducer, initialState);
    
    // useEffect 处理副作用
    useEffect(() => {
      middlewares.forEach(mw => mw.beforeRequest());
      return () => middlewares.forEach(mw => mw.afterResponse());
    }, []);
    
    return <LLMRenderer model={model} tools={tools} />;
  };
}
```

**Vue 风格思维：**
```typescript
// 就像使用 Composable
export function useSmartAgent(config: AgentConfig) {
  // 使用 Pinia 或 reactive
  const state = reactive({ messages: [], status: 'idle' });
  
  // 生命周期钩子
  onMounted(() => {
    config.middlewares.forEach(mw => mw.beforeRequest());
  });
  
  onUnmounted(() => {
    config.middlewares.forEach(mw => mw.cleanup());
  });
  
  // 提供方法给组件
  const sendMessage = async (msg: string) => {
    // 执行逻辑
  };
  
  return { state, sendMessage };
}

// 在组件中使用
export default defineComponent({
  setup() {
    const { state, sendMessage } = useSmartAgent({
      model: 'gpt-4',
      tools: [searchTool, codeTool]
    });
    
    return { state, sendMessage };
  }
});
```

#### 中间件链

**React / Express 风格：**
```typescript
// Redux Middleware 风格
const middlewareChain = [
  loggerMiddleware,
  authMiddleware,
  errorMiddleware
];

// 执行顺序：logger → auth → error → handler → error → auth → logger
```

**Vue / Pinia 风格：**
```typescript
// Pinia Plugin 风格
const pinia = createPinia();

pinia.use(({ store }) => {
  // before action
  store.$onAction(({ name, args, after, onError }) => {
    console.log('Start', name);
    
    after(() => {
      console.log('Success', name);
    });
    
    onError((error) => {
      console.error('Error', error);
    });
  });
});
```

### 3.3 组件通信对比

**React Context vs Vue Provide/Inject**

```typescript
// React Context
const MessageBranchContext = createContext(null);

function MessageBranchProvider({ children }) {
  const [currentBranch, setCurrentBranch] = useState(0);
  return (
    <MessageBranchContext.Provider value={{ currentBranch, setCurrentBranch }}>
      {children}
    </MessageBranchContext.Provider>
  );
}

function useMessageBranch() {
  return useContext(MessageBranchContext);
}
```

```typescript
// Vue Provide/Inject
// Parent.vue
export default defineComponent({
  setup() {
    const currentBranch = ref(0);
    provide('messageBranch', {
      currentBranch,
      setCurrentBranch: (n: number) => currentBranch.value = n
    });
  }
});

// Child.vue
export default defineComponent({
  setup() {
    const { currentBranch, setCurrentBranch } = inject('messageBranch');
    return { currentBranch, setCurrentBranch };
  }
});
```

## 四、中间件执行顺序详解

```
┌─────────────────────────────────────────────────────────────────┐
│                        请求流向                                 │
│                     从上到下 → 从下到上                          │
└─────────────────────────────────────────────────────────────────┘

用户请求
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│ 阶段1: 基础设施层                                            │
│                                                            │
│  [0] ThreadDataMiddleware                                  │
│      → 类比 Vue: beforeCreate + created                    │
│      → 初始化线程上下文，类似组件初始化数据                   │
│                                                            │
│  [1] UploadsMiddleware                                     │
│      → 类比 Vue: 处理 <input type="file" @change>          │
│      → 处理用户上传的文件                                   │
│                                                            │
│  [2] SandboxMiddleware                                     │
│      → 类比 Vue: 创建 Web Worker                           │
│      → 准备代码执行沙盒环境                                 │
└────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│ 阶段2: 预处理层                                              │
│                                                            │
│  [3] DanglingToolCallMiddleware                            │
│      → 类比 Vue: 处理上次未完成的 Promise                   │
│      → 修复中断的工具调用状态                               │
│                                                            │
│  [4] GuardrailMiddleware                                   │
│      → 类比 Vue: 路由守卫 beforeEach                       │
│      → 内容安全检查                                         │
│                                                            │
│  [5] ToolErrorHandlingMiddleware                           │
│      → 类比 Vue: errorCaptured                             │
│      → 统一错误处理                                         │
│                                                            │
│  [6] SummarizationMiddleware                               │
│      → 类比 Vue: 虚拟列表的窗口化计算                       │
│      → 长对话自动摘要                                       │
└────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│ 阶段3: 功能增强层                                            │
│                                                            │
│  [7] TodoMiddleware (plan_mode)                            │
│      → 类比 Vue: 任务队列管理                               │
│      → 追踪多步骤任务进度                                   │
│                                                            │
│  [8] TitleMiddleware                                       │
│      → 类比 Vue: 动态设置 document.title                   │
│      → 自动生成对话标题                                     │
│                                                            │
│  [9] MemoryMiddleware                                      │
│      → 类比 Vue: Pinia PersistedState                      │
│      → 加载用户历史记忆                                     │
│                                                            │
│  [10] ViewImageMiddleware                                  │
│      → 类比 Vue: 图片预览组件                               │
│      → 处理图片输入                                         │
│                                                            │
│  [11] SubagentLimitMiddleware                              │
│      → 类比 Vue: Promise.all 并发限制                       │
│      → 限制子任务并发数                                     │
└────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│ 阶段4: 执行控制层                                            │
│                                                            │
│  [12] LoopDetectionMiddleware                              │
│      → 类比 Vue: watch 的死循环检测                         │
│      → 检测并打断重复调用循环                               │
│                                                            │
│  [13] ClarificationMiddleware                              │
│      → 类比 Vue: 确认弹窗 $confirm                          │
│      → 拦截需要用户确认的请求                               │
└────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│                   LLM Agent 核心推理                         │
│                                                            │
│   就像 Vue 的渲染函数：输入数据 → 计算/处理 → 输出结果      │
│                                                            │
│   Input (messages) → LLM Model → Output (response)         │
└────────────────────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────┐
│ 阶段5: 后处理层（反向执行）                                   │
│                                                            │
│   [MemoryMiddleware]   → 保存新记忆                        │
│   [TitleMiddleware]    → 更新对话标题                      │
│                                                            │
│   类比 Vue: afterEach 路由守卫 / onUpdated 钩子            │
└────────────────────────────────────────────────────────────┘
    │
    ▼
  返回响应
```

## 五、数据流向图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              前端层                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        Vue / React                               │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │   │
│  │  │   Template  │    │   Script    │    │      Styles         │ │   │
│  │  │  (UI 渲染)   │◀───│  (逻辑处理)  │◀───│   (样式定义)         │ │   │
│  │  └──────┬──────┘    └──────┬──────┘    └─────────────────────┘ │   │
│  │         │                  │                                     │   │
│  │         │           ┌──────▼──────┐                             │   │
│  │         │           │  Composables │  ← useChat, useThread      │   │
│  │         │           │  / Hooks     │                             │   │
│  │         │           └──────┬──────┘                             │   │
│  │         │                  │                                     │   │
│  │         └──────────────────┘                                     │   │
│  │                            │                                     │   │
│  └────────────────────────────┼─────────────────────────────────────┘   │
│                               │ HTTP / SSE                               │
└───────────────────────────────┼─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              网关层                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    FastAPI (类似 Express)                        │   │
│  │                                                                 │   │
│  │  @app.get("/api/models")      → 获取可用模型                    │   │
│  │  @app.post("/api/runs/stream") → 流式对话                      │   │
│  │  @app.get("/api/threads/{id}") → 获取对话历史                  │   │
│  │                                                                 │   │
│  │  类比 Vue: 路由配置 (vue-router)                                │   │
│  │  const routes = [                                              │   │
│  │    { path: '/api/models', component: ModelsHandler },          │   │
│  │    { path: '/api/runs/stream', component: StreamHandler }      │   │
│  │  ]                                                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Agent 核心                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                 │   │
│  │   Factory Pattern (工厂模式)                                    │   │
│  │   ┌─────────────────────────────────────────────────────────┐  │   │
│  │   │  make_lead_agent(config)                                │  │   │
│  │   │  ├── 解析配置 (类似 Vue 的 props 默认值处理)              │  │   │
│  │   │  ├── 创建模型 (类似创建 API 客户端实例)                  │  │   │
│  │   │  ├── 组装中间件 (类似 app.use(middleware))              │  │   │
│  │   │  └── 返回 Agent 实例 (类似返回组件实例)                  │  │   │
│  │   └─────────────────────────────────────────────────────────┘  │   │
│  │                                                                 │   │
│  │   State Management (状态管理)                                   │   │
│  │   ┌─────────────────────────────────────────────────────────┐  │   │
│  │   │  ThreadState {  // 类似 Vue 的 reactive()               │  │   │
│  │   │    messages: [],    // 消息列表                         │  │   │
│  │   │    metadata: {},    // 元数据                           │  │   │
│  │   │    checkpoint: {}   // 检查点                           │  │   │
│  │   │  }                                                      │  │   │
│  │   └─────────────────────────────────────────────────────────┘  │   │
│  │                                                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
            ┌──────────┐  ┌──────────┐  ┌──────────┐
            │  Tools   │  │ Sandbox  │  │   DB     │
            │ (Skills) │  │(代码执行) │  │(PostgreSQL)
            └──────────┘  └──────────┘  └──────────┘
```

## 六、启动流程

```
┌─────────────┐
│   启动命令   │
│ uvicorn /   │
│ docker run  │
└──────┬──────┘
       │
       ▼
┌────────────────────────────────────────────────────────────┐
│ 1. 加载配置                                                  │
│    - 读取 config.yaml                                       │
│    - 验证环境变量                                           │
│    - 类比 Vue: 加载 vite.config.ts + .env                   │
└────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────┐
│ 2. 初始化 Lifespan                                          │
│    - 类似 Vue App 的 beforeCreate → created                 │
│    - 初始化数据库连接                                        │
│    - 初始化 LangGraph Runtime                               │
└────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────┐
│ 3. 启动服务                                                  │
│    - 注册路由 (类似 Vue Router 注册路由)                    │
│    - 开始监听端口                                            │
│    - 类比 Vue: app.mount('#app')                            │
└────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────┐
│ 4. 接收请求                                                  │
│    - 进入请求处理循环                                        │
│    - 类比 Vue: 响应用户交互                                  │
└────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────┐
│ 5. 关闭服务                                                  │
│    - Lifespan shutdown (类似 Vue 的 beforeUnmount)          │
│    - 关闭数据库连接                                          │
│    - 清理资源                                                │
└────────────────────────────────────────────────────────────┘
```

## 七、文件组织速查

```
deer-flow/
├── frontend/                    # 前端层
│   ├── src/
│   │   ├── app/                # Next.js App Router
│   │   │   ├── layout.tsx      # 根布局 (类比 Vue App.vue)
│   │   │   ├── page.tsx        # 首页
│   │   │   └── workspace/      # 工作区路由
│   │   │
│   │   ├── components/         # 组件
│   │   │   ├── ai-elements/    # AI 组件
│   │   │   │   ├── message.tsx # 消息组件
│   │   │   │   └── ...
│   │   │   └── ui/             # UI 基础组件
│   │   │
│   │   └── composables/        # Vue: composables
│   │       └── (React: hooks)  # 逻辑复用
│   │
│   └── package.json
│
├── backend/                     # 后端层
│   ├── app/gateway/
│   │   ├── app.py              # 入口 (类比 Vue main.ts)
│   │   └── routers/            # 路由 (类比 Vue Router)
│   │
│   └── packages/harness/deerflow/
│       ├── agents/
│       │   ├── factory.py      # 组件工厂
│       │   ├── lead_agent/
│       │   │   └── agent.py    # 主 Agent
│       │   └── middlewares/    # 中间件
│       │
│       ├── config/             # 配置
│       ├── models/             # 模型定义
│       ├── tools/              # 工具
│       └── sandbox/            # 沙盒
│
└── docker/                      # 部署配置
```

---

## 总结

DeerFlow 的架构可以用前端框架类比理解：

1. **Gateway** = Vue Router + Express 后端路由
2. **Agent Factory** = Vue Composables / React Hooks 工厂
3. **Middleware Chain** = Pinia Plugins / Redux Middleware
4. **StateGraph** = Pinia Store / Redux Store
5. **Checkpointer** = Pinia PersistedState / Redux Persist
6. **Lifespan** = Vue 生命周期钩子 (onMounted/onUnmounted)

核心设计模式：**组合优于继承**，通过中间件链灵活组装功能，就像 Vue 3 的 Composition API 通过组合函数构建复杂逻辑。
