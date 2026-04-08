"use client";

import { useCallback, useEffect, useState } from "react";

import { type PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { ArtifactTrigger } from "@/components/workspace/artifacts";
import {
  ChatBox,
  useSpecificChatMode,
  useThreadChat,
} from "@/components/workspace/chats";
import { ExportTrigger } from "@/components/workspace/export-trigger";
import { InputBox } from "@/components/workspace/input-box";
import {
  MessageList,
  MESSAGE_LIST_DEFAULT_PADDING_BOTTOM,
  MESSAGE_LIST_FOLLOWUPS_EXTRA_PADDING_BOTTOM,
} from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { TokenUsageIndicator } from "@/components/workspace/token-usage-indicator";
import { Welcome } from "@/components/workspace/welcome";
import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { useThreadSettings } from "@/core/settings";
import { useThreadStream } from "@/core/threads/hooks";
import { textOfMessage } from "@/core/threads/utils";
import { env } from "@/env";
import { cn } from "@/lib/utils";

// 通用聊天页：整合消息流、上下文设置、通知与输入区，是会话体验的主容器。
// 学习提示：`ThreadContext.Provider` 可类比 Vue 的 provide/inject，用于跨层传递线程状态。
export default function ChatPage() {
  const { t } = useI18n();
  // 跟进问题区域是否展开，会影响消息列表底部留白。
  const [showFollowups, setShowFollowups] = useState(false);
  // 会话 ID 与“是否新会话”由专用 hook 管理，页面只消费状态。
  const { threadId, setThreadId, isNewThread, setIsNewThread, isMock } =
    useThreadChat();
  // 线程设置（如上下文模式）可类比 Vue + Pinia 的局部 store。
  const [settings, setSettings] = useThreadSettings(threadId);
  const [mounted, setMounted] = useState(false);
  useSpecificChatMode();

  // 生命周期提示：只在客户端首帧后置为 true，避免 SSR 与客户端渲染不一致。
  // 可类比 Vue 的 `onMounted` 后再访问依赖浏览器环境的能力。
  useEffect(() => {
    setMounted(true);
  }, []);

  const { showNotification } = useNotification();

  const [thread, sendMessage, isUploading] = useThreadStream({
    // 新建会话时先不传 threadId，等待后端创建并回填。
    threadId: isNewThread ? undefined : threadId,
    context: settings.context,
    isMock,
    onStart: (createdThreadId) => {
      setThreadId(createdThreadId);
      setIsNewThread(false);
      // 特殊处理（hack）说明：这里刻意不用 Next Router 跳转。
      // 原因：路由跳转会触发页面重挂载，流式输出中的本地状态可能丢失。
      // 因此改用原生 history.replaceState，仅更新地址栏而不重建组件树。
      history.replaceState(null, "", `/workspace/chats/${createdThreadId}`);
    },
    onFinish: (state) => {
      if (document.hidden || !document.hasFocus()) {
        let body = "Conversation finished";
        const lastMessage = state.messages.at(-1);
        if (lastMessage) {
          const textContent = textOfMessage(lastMessage);
          if (textContent) {
            body =
              textContent.length > 200
                ? textContent.substring(0, 200) + "..."
                : textContent;
          }
        }
        showNotification(state.title, { body });
      }
    },
  });

  // 组件通信提示：`InputBox` 通过 onSubmit 把输入上抛到页面，再统一发送到消息流。
  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      void sendMessage(threadId, message);
    },
    [sendMessage, threadId],
  );

  // 错误与中断控制：停止流式输出由统一入口触发，便于后续扩展重试逻辑。
  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);

  const messageListPaddingBottom = showFollowups
    ? MESSAGE_LIST_DEFAULT_PADDING_BOTTOM +
      MESSAGE_LIST_FOLLOWUPS_EXTRA_PADDING_BOTTOM
    : undefined;

  return (
    <ThreadContext.Provider value={{ thread, isMock }}>
      <ChatBox threadId={threadId}>
        <div className="relative flex size-full min-h-0 justify-between">
          <header
            className={cn(
              "absolute top-0 right-0 left-0 z-30 flex h-12 shrink-0 items-center px-4",
              isNewThread
                ? "bg-background/0 backdrop-blur-none"
                : "bg-background/80 shadow-xs backdrop-blur",
            )}
          >
            <div className="flex w-full items-center text-sm font-medium">
              <ThreadTitle threadId={threadId} thread={thread} />
            </div>
            <div className="flex items-center gap-2">
              <TokenUsageIndicator messages={thread.messages} />
              <ExportTrigger threadId={threadId} />
              <ArtifactTrigger />
            </div>
          </header>
          <main className="flex min-h-0 max-w-full grow flex-col">
            <div className="flex size-full justify-center">
              <MessageList
                className={cn("size-full", !isNewThread && "pt-10")}
                threadId={threadId}
                thread={thread}
                paddingBottom={messageListPaddingBottom}
              />
            </div>
            <div className="absolute right-0 bottom-0 left-0 z-30 flex justify-center px-4">
              <div
                className={cn(
                  "relative w-full",
                  isNewThread && "-translate-y-[calc(50vh-96px)]",
                  isNewThread
                    ? "max-w-(--container-width-sm)"
                    : "max-w-(--container-width-md)",
                )}
              >
                <div className="absolute -top-4 right-0 left-0 z-0">
                  <div className="absolute right-0 bottom-0 left-0">
                    <TodoList
                      className="bg-background/5"
                      todos={thread.values.todos ?? []}
                      hidden={
                        !thread.values.todos || thread.values.todos.length === 0
                      }
                    />
                  </div>
                </div>
                {mounted ? (
                  <InputBox
                    className={cn("bg-background/5 w-full -translate-y-4")}
                    isNewThread={isNewThread}
                    threadId={threadId}
                    autoFocus={isNewThread}
                    status={
                      thread.error
                        ? "error"
                        : thread.isLoading
                          ? "streaming"
                          : "ready"
                    }
                    context={settings.context}
                    extraHeader={
                      isNewThread && <Welcome mode={settings.context.mode} />
                    }
                    disabled={
                      env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ||
                      isUploading
                    }
                    onContextChange={(context) =>
                      setSettings("context", context)
                    }
                    onFollowupsVisibilityChange={setShowFollowups}
                    onSubmit={handleSubmit}
                    onStop={handleStop}
                  />
                ) : (
                  <div
                    aria-hidden="true"
                    className={cn(
                      "bg-background/5 h-32 w-full -translate-y-4 rounded-2xl border",
                    )}
                  />
                )}
                {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                  <div className="text-muted-foreground/67 w-full translate-y-12 text-center text-xs">
                    {t.common.notAvailableInDemoMode}
                  </div>
                )}
              </div>
            </div>
          </main>
        </div>
      </ChatBox>
    </ThreadContext.Provider>
  );
}
