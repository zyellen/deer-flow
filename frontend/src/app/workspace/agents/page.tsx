import { AgentGallery } from "@/components/workspace/agents/agent-gallery";

// Agent 广场页：页面层仅作为容器，把展示与交互逻辑交给 AgentGallery。
// 学习提示：类似 Vue 中“页面组件 + 展示组件”分层，方便复用与测试。
export default function AgentsPage() {
  return <AgentGallery />;
}
