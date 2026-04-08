"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useI18n } from "@/core/i18n/hooks";
import { useThreads } from "@/core/threads/hooks";
import { pathOfThread, titleOfThread } from "@/core/threads/utils";
import { formatTimeAgo } from "@/core/utils/datetime";

// 会话列表页：负责展示历史线程并提供本地搜索。
// 学习提示：`search` + `onChange` 的组合可类比 Vue 的 `v-model` 双向绑定。
export default function ChatsPage() {
  const { t } = useI18n();
  const { data: threads } = useThreads();
  const [search, setSearch] = useState("");

  // 副作用：根据当前语言文案更新浏览器标题。
  // 可类比 Vue 的 `onMounted/onUpdated` 中同步 document.title 的做法。
  useEffect(() => {
    document.title = `${t.pages.chats} - ${t.pages.appName}`;
  }, [t.pages.chats, t.pages.appName]);

  // 计算属性：仅当线程列表或搜索词变化时重新计算，避免每次渲染全量过滤。
  // 可类比 Vue 的 `computed`。
  const filteredThreads = useMemo(() => {
    return threads?.filter((thread) => {
      return titleOfThread(thread).toLowerCase().includes(search.toLowerCase());
    });
  }, [threads, search]);

  return (
    <WorkspaceContainer>
      <WorkspaceHeader></WorkspaceHeader>
      <WorkspaceBody>
        <div className="flex size-full flex-col">
          <header className="flex shrink-0 items-center justify-center pt-8">
            <Input
              type="search"
              className="h-12 w-full max-w-(--container-width-md) text-xl"
              placeholder={t.chats.searchChats}
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </header>
          <main className="min-h-0 flex-1">
            <ScrollArea className="size-full py-4">
              <div className="mx-auto flex size-full max-w-(--container-width-md) flex-col">
                {filteredThreads?.map((thread) => (
                  <Link
                    key={thread.thread_id}
                    href={pathOfThread(thread.thread_id)}
                  >
                    <div className="flex flex-col gap-2 border-b p-4">
                      <div>
                        <div>{titleOfThread(thread)}</div>
                      </div>
                      {thread.updated_at && (
                        <div className="text-muted-foreground text-sm">
                          {formatTimeAgo(thread.updated_at)}
                        </div>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            </ScrollArea>
          </main>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
