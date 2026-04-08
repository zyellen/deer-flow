"use client";

import {
  ArrowLeftIcon,
  BotIcon,
  CheckCircleIcon,
  InfoIcon,
  MoreHorizontalIcon,
  SaveIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  PromptInput,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ArtifactsProvider } from "@/components/workspace/artifacts";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import type { Agent } from "@/core/agents";
import {
  AgentNameCheckError,
  checkAgentName,
  createAgent,
  getAgent,
} from "@/core/agents/api";
import { useI18n } from "@/core/i18n/hooks";
import { useThreadStream } from "@/core/threads/hooks";
import { uuid } from "@/core/utils/uuid";
import { isIMEComposing } from "@/lib/ime";
import { cn } from "@/lib/utils";

// 页面状态机：先命名（name），再进入引导聊天（chat）。
type Step = "name" | "chat";
// setup_agent 工具调用状态：空闲 -> 已请求 -> 已完成。
type SetupAgentStatus = "idle" | "requested" | "completed";

// Agent 名称仅允许字母、数字、连字符，便于作为稳定标识符使用。
const NAME_RE = /^[A-Za-z0-9-]+$/;
// 本地存储键：用于“保存提示”只展示一次。
const SAVE_HINT_STORAGE_KEY = "deerflow.agent-create.save-hint-seen";
// 重试退避时间（毫秒）：应对“创建后立即读取”时的短暂最终一致性延迟。
const AGENT_READ_RETRY_DELAYS_MS = [200, 500, 1_000, 2_000];

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

// 关键逻辑：读取 Agent 的“带退避重试”策略。
// 通俗解释：刚写入完成时，读请求可能短时间拿不到数据；这里按 0/200/500/1000/2000ms 逐步重试。
// 学习提示：这和前端轮询等待后端状态稳定类似。
async function getAgentWithRetry(agentName: string) {
  for (const delay of [0, ...AGENT_READ_RETRY_DELAYS_MS]) {
    if (delay > 0) {
      await wait(delay);
    }

    try {
      return await getAgent(agentName);
    } catch {
      // 特殊处理：这里故意吞掉单次读取错误，交给后续重试统一兜底。
      // 原因：此阶段最常见是暂时不可读，直接报错会打断正常创建流程。
    }
  }

  return null;
}

function getCreateAgentErrorMessage(
  error: unknown,
  networkErrorMessage: string,
  fallbackMessage: string,
) {
  if (error instanceof TypeError && error.message === "Failed to fetch") {
    return networkErrorMessage;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallbackMessage;
}

// 新建 Agent 页面：采用“命名 -> 引导聊天 -> 保存”的分步交互。
// 学习提示：这里多个 `useState` 的组合，可类比 Vue 组合式 API 中多个 `ref`。
export default function NewAgentPage() {
  const { t } = useI18n();
  const router = useRouter();

  const [step, setStep] = useState<Step>("name");
  // 受控输入：行为可类比 Vue 的 `v-model`，输入变化与状态始终同步。
  const [nameInput, setNameInput] = useState("");
  const [nameError, setNameError] = useState("");
  const [isCheckingName, setIsCheckingName] = useState(false);
  const [isCreatingAgent, setIsCreatingAgent] = useState(false);
  const [agentName, setAgentName] = useState("");
  const [agent, setAgent] = useState<Agent | null>(null);
  const [showSaveHint, setShowSaveHint] = useState(false);
  const [setupAgentStatus, setSetupAgentStatus] =
    useState<SetupAgentStatus>("idle");

  const threadId = useMemo(() => uuid(), []);

  const [thread, sendMessage] = useThreadStream({
    // 只有进入聊天步骤才真正开启线程，避免命名步骤提前触发会话资源。
    threadId: step === "chat" ? threadId : undefined,
    context: {
      mode: "flash",
      // 引导模式标识：通知后端这是创建 Agent 的 bootstrap 会话。
      is_bootstrap: true,
    },
    onFinish() {
      // 兜底状态恢复：若保存流程未落库成功，回到 idle，避免按钮一直锁定。
      if (!agent && setupAgentStatus === "requested") {
        setSetupAgentStatus("idle");
      }
    },
    onToolEnd({ name }) {
      // 组件通信提示：工具执行结束事件由线程层上抛到页面层统一处理。
      if (name !== "setup_agent" || !agentName) return;
      setSetupAgentStatus("completed");
      void getAgentWithRetry(agentName).then((fetched) => {
        if (fetched) {
          setAgent(fetched);
          return;
        }

        toast.error(t.agents.agentCreatedPendingRefresh);
      });
    },
  });

  // 生命周期提示：切换到聊天步骤后，再决定是否展示“一次性保存提示”。
  // 这类“进入页面后触发”的逻辑可类比 Vue 的 `onMounted` + 本地缓存判断。
  useEffect(() => {
    if (typeof window === "undefined" || step !== "chat") {
      return;
    }
    if (window.localStorage.getItem(SAVE_HINT_STORAGE_KEY) === "1") {
      return;
    }
    setShowSaveHint(true);
    window.localStorage.setItem(SAVE_HINT_STORAGE_KEY, "1");
  }, [step]);

  // 关键流程：名称校验 -> 可用性检查 -> 创建 Agent -> 进入引导聊天。
  // 错误处理策略：每个可能失败的网络步骤都给出明确、友好的提示文案。
  const handleConfirmName = useCallback(async () => {
    const trimmed = nameInput.trim();
    if (!trimmed) return;
    if (!NAME_RE.test(trimmed)) {
      setNameError(t.agents.nameStepInvalidError);
      return;
    }

    setNameError("");
    setIsCheckingName(true);
    try {
      const result = await checkAgentName(trimmed);
      if (!result.available) {
        setNameError(t.agents.nameStepAlreadyExistsError);
        return;
      }
    } catch (err) {
      if (
        err instanceof AgentNameCheckError &&
        err.reason === "backend_unreachable"
      ) {
        setNameError(t.agents.nameStepNetworkError);
      } else {
        setNameError(t.agents.nameStepCheckError);
      }
      return;
    } finally {
      setIsCheckingName(false);
    }

    setIsCreatingAgent(true);
    try {
      await createAgent({
        name: trimmed,
        description: "",
        soul: "",
      });
    } catch (err) {
      setNameError(
        getCreateAgentErrorMessage(
          err,
          t.agents.nameStepNetworkError,
          t.agents.nameStepCheckError,
        ),
      );
      return;
    } finally {
      setIsCreatingAgent(false);
    }

    setAgentName(trimmed);
    setStep("chat");
    await sendMessage(threadId, {
      text: t.agents.nameStepBootstrapMessage.replace("{name}", trimmed),
      files: [],
    });
  }, [
    nameInput,
    sendMessage,
    t.agents.nameStepAlreadyExistsError,
    t.agents.nameStepNetworkError,
    t.agents.nameStepBootstrapMessage,
    t.agents.nameStepCheckError,
    t.agents.nameStepInvalidError,
    threadId,
  ]);

  const handleNameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !isIMEComposing(e)) {
      e.preventDefault();
      void handleConfirmName();
    }
  };

  // 聊天提交：把当前输入与目标 agent_name 绑定后发送到同一线程。
  const handleChatSubmit = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || thread.isLoading) return;
      await sendMessage(
        threadId,
        { text: trimmed, files: [] },
        { agent_name: agentName },
      );
    },
    [agentName, sendMessage, thread.isLoading, threadId],
  );

  // 保存动作：通过隐藏消息触发后端 setup_agent 工具，不污染聊天可见记录。
  const handleSaveAgent = useCallback(async () => {
    if (
      !agentName ||
      agent ||
      thread.isLoading ||
      setupAgentStatus !== "idle"
    ) {
      return;
    }

    setSetupAgentStatus("requested");
    setShowSaveHint(false);
    try {
      await sendMessage(
        threadId,
        { text: t.agents.saveCommandMessage, files: [] },
        { agent_name: agentName },
        { additionalKwargs: { hide_from_ui: true } },
      );
      toast.success(t.agents.saveRequested);
    } catch (error) {
      setSetupAgentStatus("idle");
      toast.error(error instanceof Error ? error.message : String(error));
    }
  }, [
    agent,
    agentName,
    sendMessage,
    setupAgentStatus,
    t.agents.saveCommandMessage,
    t.agents.saveRequested,
    thread.isLoading,
    threadId,
  ]);

  const header = (
    <header className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => router.push("/workspace/agents")}
        >
          <ArrowLeftIcon className="h-4 w-4" />
        </Button>
        <h1 className="text-sm font-semibold">{t.agents.createPageTitle}</h1>
      </div>

      {step === "chat" ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={t.agents.more}>
              <MoreHorizontalIcon className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={() => void handleSaveAgent()}
              disabled={
                !!agent || thread.isLoading || setupAgentStatus !== "idle"
              }
            >
              <SaveIcon className="h-4 w-4" />
              {setupAgentStatus === "requested"
                ? t.agents.saving
                : t.agents.save}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </header>
  );

  if (step === "name") {
    return (
      <div className="flex size-full flex-col">
        {header}
        <main className="flex flex-1 flex-col items-center justify-center px-4">
          <div className="w-full max-w-sm space-y-8">
            <div className="space-y-3 text-center">
              <div className="bg-primary/10 mx-auto flex h-14 w-14 items-center justify-center rounded-full">
                <BotIcon className="text-primary h-7 w-7" />
              </div>
              <div className="space-y-1">
                <h2 className="text-xl font-semibold">
                  {t.agents.nameStepTitle}
                </h2>
                <p className="text-muted-foreground text-sm">
                  {t.agents.nameStepHint}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <Input
                autoFocus
                placeholder={t.agents.nameStepPlaceholder}
                value={nameInput}
                onChange={(e) => {
                  setNameInput(e.target.value);
                  setNameError("");
                }}
                onKeyDown={handleNameKeyDown}
                className={cn(nameError && "border-destructive")}
              />
              {nameError ? (
                <p className="text-destructive text-sm">{nameError}</p>
              ) : null}
              <Button
                className="w-full"
                onClick={() => void handleConfirmName()}
                disabled={
                  !nameInput.trim() || isCheckingName || isCreatingAgent
                }
              >
                {t.agents.nameStepContinue}
              </Button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    // 组件通信提示：线程状态通过 Context 向下游消息组件共享，可类比 Vue 的 provide/inject。
    <ThreadContext.Provider value={{ thread }}>
      <ArtifactsProvider>
        <div className="flex size-full flex-col">
          {header}

          <main className="flex min-h-0 flex-1 flex-col">
            {showSaveHint ? (
              <div className="px-4 pt-4">
                <div className="mx-auto w-full max-w-(--container-width-md)">
                  <Alert>
                    <InfoIcon className="h-4 w-4" />
                    <AlertDescription>{t.agents.saveHint}</AlertDescription>
                  </Alert>
                </div>
              </div>
            ) : null}

            <div className="flex min-h-0 flex-1 justify-center">
              <MessageList
                className={cn("size-full", showSaveHint ? "pt-4" : "pt-10")}
                threadId={threadId}
                thread={thread}
              />
            </div>

            <div className="bg-background flex shrink-0 justify-center border-t px-4 py-4">
              <div className="w-full max-w-(--container-width-md)">
                {agent ? (
                  <div className="flex flex-col items-center gap-4 rounded-2xl border py-8 text-center">
                    <CheckCircleIcon className="text-primary h-10 w-10" />
                    <p className="font-semibold">{t.agents.agentCreated}</p>
                    <div className="flex gap-2">
                      <Button
                        onClick={() =>
                          router.push(
                            `/workspace/agents/${agentName}/chats/new`,
                          )
                        }
                      >
                        {t.agents.startChatting}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => router.push("/workspace/agents")}
                      >
                        {t.agents.backToGallery}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <PromptInput
                    onSubmit={({ text }) => void handleChatSubmit(text)}
                  >
                    <PromptInputTextarea
                      autoFocus
                      placeholder={t.agents.createPageSubtitle}
                      disabled={thread.isLoading}
                    />
                    <PromptInputFooter className="justify-end">
                      <PromptInputSubmit disabled={thread.isLoading} />
                    </PromptInputFooter>
                  </PromptInput>
                )}
              </div>
            </div>
          </main>
        </div>
      </ArtifactsProvider>
    </ThreadContext.Provider>
  );
}
