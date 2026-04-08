import { Footer } from "@/components/landing/footer";
import { Header } from "@/components/landing/header";
import { Hero } from "@/components/landing/hero";
import { CaseStudySection } from "@/components/landing/sections/case-study-section";
import { CommunitySection } from "@/components/landing/sections/community-section";
import { SandboxSection } from "@/components/landing/sections/sandbox-section";
import { SkillsSection } from "@/components/landing/sections/skills-section";
import { WhatsNewSection } from "@/components/landing/sections/whats-new-section";

// Landing 首页：负责按顺序拼装各个营销区块，组件本身只做“编排”，不承载业务状态。
// 学习提示：这和 Vue 中在模板里组合多个子组件类似，页面层保持“薄”，逻辑尽量下沉到子组件。
export default function LandingPage() {
  return (
    <div className="min-h-screen w-full bg-[#0a0a0a]">
      {/* 顶部导航：全站入口与主要操作 */}
      <Header />
      <main className="flex w-full flex-col">
        {/* 主视觉区：第一屏价值说明 */}
        <Hero />
        {/* 案例展示：增强可信度 */}
        <CaseStudySection />
        {/* 能力说明：展示技能体系 */}
        <SkillsSection />
        {/* 交互体验：沙盒演示 */}
        <SandboxSection />
        {/* 版本更新：近期变化 */}
        <WhatsNewSection />
        {/* 社区入口：引导用户参与 */}
        <CommunitySection />
      </main>
      {/* 页脚：补充链接与版权信息 */}
      <Footer />
    </div>
  );
}
