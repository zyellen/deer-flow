import fs from "fs";
import path from "path";

import { redirect } from "next/navigation";

import { env } from "@/env";

// Workspace 首页路由：只负责“分发”到具体会话页，不直接渲染 UI。
// 学习提示：这相当于 Vue Router 里的重定向守卫，根据环境把用户导向不同页面。
export default function WorkspacePage() {
  if (env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true") {
    // 静态演示模式下，从 demo 目录中挑选一个可用线程作为默认落点。
    const firstThread = fs
      .readdirSync(path.resolve(process.cwd(), "public/demo/threads"), {
        withFileTypes: true,
      })
      .find((thread) => thread.isDirectory() && !thread.name.startsWith("."));
    if (firstThread) {
      return redirect(`/workspace/chats/${firstThread.name}`);
    }
  }

  // 兜底逻辑：若不在静态模式，或未找到 demo 线程，则进入新建会话页。
  return redirect("/workspace/chats/new");
}
