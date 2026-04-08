/**
 * 根布局组件 (Root Layout) - 整个应用的"外壳"
 *
 * 【核心概念】
 * 这是 Next.js 13+ App Router 的根布局，相当于传统 React 应用的 App 组件
 * 所有页面都会在这个布局内部渲染
 *
 * 【比喻理解】
 * 想象你在搭建一个房子的框架：
 * - RootLayout = 房子的主体结构（地基、墙壁、屋顶）
 * - children = 每个房间的具体装修（各个页面的内容）
 * - Providers = 全屋的基础设施（电路、水管、WiFi）
 *
 * 【Provider 嵌套顺序】（从外到内）
 * ThemeProvider → I18nProvider → Page Content
 * 就像洋葱模型，每一层都提供特定的全局能力
 *
 * 【关键技术点】
 * - async 组件：Next.js 支持在服务端获取数据
 * - suppressHydrationWarning：防止主题切换时的 hydration 不匹配警告
 * - 服务端渲染：locale 检测在服务端完成，提升首屏性能
 */

// 全局样式导入（必须最先导入，确保 CSS 优先级）
import "@/styles/globals.css";

// KaTeX 数学公式渲染样式
// 用于渲染 LaTeX 格式的数学公式，如 $E=mc^2$
import "katex/dist/katex.min.css";

import { type Metadata } from "next";

// 主题管理 Provider - 处理暗黑/亮色模式切换
// 类似于使用 next-themes 或自定义的主题上下文
import { ThemeProvider } from "@/components/theme-provider";

// 国际化 Provider - 管理多语言切换
// 提供 t() 翻译函数和当前语言状态
import { I18nProvider } from "@/core/i18n/context";

// 服务端语言检测函数
// 根据请求头或 cookie 自动检测用户语言偏好
import { detectLocaleServer } from "@/core/i18n/server";

/**
 * 页面元数据配置
 * 用于 SEO 和浏览器标签页显示
 * Next.js 会自动注入到 <head> 中
 */
export const metadata: Metadata = {
  title: "DeerFlow - AI Agent 工作流平台",
  description: "基于 LangChain 构建的超级智能体框架，支持工具调用、多步推理和沙箱执行",
};

/**
 * 根布局组件
 * @param children - 子页面内容，由 Next.js 路由系统自动传入
 */
export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // 服务端检测用户语言偏好
  // 这比客户端检测更早执行，避免闪烁
  const locale = await detectLocaleServer();

  return (
    // lang 属性对可访问性和 SEO 很重要
    // suppressHydrationWarning 防止主题切换时的警告
    <html
      lang={locale}
      suppressContentEditableWarning
      suppressHydrationWarning
    >
      <body>
        {/**
         * ThemeProvider: 主题管理
         * - attribute="class": 通过 CSS 类切换主题（dark/light）
         * - enableSystem: 支持跟随系统主题
         * - disableTransitionOnChange: 切换时禁用过渡动画，避免闪烁
         *
         * 类似：<ThemeProvider defaultTheme="system">
         */}
        <ThemeProvider
          attribute="class"
          enableSystem
          disableTransitionOnChange
        >
          {/**
           * I18nProvider: 国际化管理
           * - 提供翻译函数和语言切换能力
           * - 将 locale 传递到客户端上下文
           *
           * 类似：
           * <I18nextProvider i18n={i18n}>
           *   <LocaleContext.Provider value={locale}>
           */}
          <I18nProvider initialLocale={locale}>
            {children}
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
