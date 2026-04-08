/**
 * 消息组件模块 - 聊天界面的核心 UI 组件
 *
 * 【架构说明】
 * 这是一个"复合组件"(Compound Component)设计模式的实现
 * 类似于 Radix UI 或 Headless UI 的设计思路
 *
 * 【组件层级】（从外到内）
 * Message (容器)
 *   ├── MessageContent (消息内容区)
 *   │     └── MessageResponse (Markdown 渲染)
 *   ├── MessageAttachments (附件列表)
 *   │     └── MessageAttachment (单个附件)
 *   └── MessageToolbar (操作工具栏)
 *         └── MessageActions (操作按钮组)
 *
 * 【复合组件模式理解】
 * 这就像 HTML 的 table 元素家族：
 * <table>
 *   <thead>...</thead>
 *   <tbody>...</tbody>
 * </table>
 *
 * 每个子组件都是父组件的"命名空间成员"：
 * - Message.Content
 * - Message.Attachments
 * - Message.Toolbar
 * 这样的 API 设计清晰表达了组件间的层级关系
 *
 * 【分支消息功能】
 * MessageBranch 实现了类似 Git 分支的消息历史管理：
 * - 一个问题的多种回答版本可以像分支一样切换
 * - 使用 Context API 在组件树中共享分支状态
 */

"use client";

// UI 基础组件
import { Button } from "@/components/ui/button";
import { ButtonGroup, ButtonGroupText } from "@/components/ui/button-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// 工具函数
import { cn } from "@/lib/utils";

// AI SDK 类型定义
import type { FileUIPart, UIMessage } from "ai";

// Lucide 图标
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PaperclipIcon,
  XIcon,
} from "lucide-react";

// React 核心 API
import type { ComponentProps, HTMLAttributes, ReactElement } from "react";
import { createContext, memo, useContext, useEffect, useState } from "react";

// Markdown 流式渲染组件
// 用于实时显示 AI 正在生成的内容
import { Streamdown } from "streamdown";

// =============================================================================
// Message 主容器组件
// =============================================================================

/**
 * 消息组件 Props
 * @property from - 消息发送者角色："user" | "assistant" | "system"
 */
export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage["role"];
};

/**
 * 消息容器组件
 *
 * 【核心职责】
 * 提供消息的视觉框架，根据发送者角色应用不同样式
 *
 * 【样式逻辑】
 * - 用户消息：右对齐，气泡样式（类似微信的绿色气泡）
 * - AI 消息：左对齐，纯文本样式（类似微信的白色气泡）
 *
 * 【CSS 类名策略】
 * 使用 data-attribute 或特殊类名标记状态：
 * - is-user: 用户消息标记
 * - is-assistant: AI 消息标记
 * 这样子组件可以通过 CSS 选择器响应父组件状态
 */
export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    className={cn(
      // 基础布局：垂直排列，全宽
      "group flex w-full flex-col gap-2",
      // 用户消息：右对齐
      from === "user" ? "is-user ml-auto justify-end" : "is-assistant",
      className,
    )}
    {...props}
  />
);

// =============================================================================
// MessageContent 内容区组件
// =============================================================================

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

/**
 * 消息内容区组件
 *
 * 【核心职责】
 * 渲染消息的文本/富文本内容，处理不同角色的样式差异
 *
 * 【CSS 技巧解析】
 * 使用 Tailwind 的 group 变体和自定义选择器：
 *
 * 1. "group-[.is-user]:bg-secondary"
 *    - 当父元素有 is-user 类时，应用 bg-secondary
 *    - 类似 CSS：.is-user .message-content { background: secondary; }
 *
 * 2. "group-[.is-assistant]:text-foreground"
 *    - AI 消息使用默认文字颜色
 *
 * 3. "w-fit max-w-full min-w-0"
 *    - 宽度自适应内容，但不超过容器
 *    - min-w-0 防止 flex item 溢出
 *
 * 【设计参考】
 * 类似微信/飞书的消息气泡设计：
 * - 用户消息：有色背景，圆角，内边距
 * - AI 消息：透明背景，保留默认排版
 */
export const MessageContent = ({
  children,
  className,
  ...props
}: MessageContentProps) => (
  <div
    className={cn(
      // 基础布局：自适应宽度，防止溢出
      "is-user:dark flex w-fit max-w-full min-w-0 flex-col gap-2 overflow-visible",
      // 用户消息：隐藏溢出（配合圆角）
      "group-[.is-user]:overflow-hidden",
      // 用户消息样式：背景、文字、边距、圆角
      "group-[.is-user]:bg-secondary group-[.is-user]:text-foreground group-[.is-user]:ml-auto group-[.is-user]:rounded-lg group-[.is-user]:px-4 group-[.is-user]:py-3",
      // AI 消息样式：默认文字颜色
      "group-[.is-assistant]:text-foreground",
      className,
    )}
    {...props}
  >
    {children}
  </div>
);

export type MessageActionsProps = ComponentProps<"div">;

export const MessageActions = ({
  className,
  children,
  ...props
}: MessageActionsProps) => (
  <div className={cn("flex items-center gap-1", className)} {...props}>
    {children}
  </div>
);

export type MessageActionProps = ComponentProps<typeof Button> & {
  tooltip?: string;
  label?: string;
};

export const MessageAction = ({
  tooltip,
  children,
  label,
  variant = "ghost",
  size = "icon-sm",
  ...props
}: MessageActionProps) => {
  const button = (
    <Button size={size} type="button" variant={variant} {...props}>
      {children}
      <span className="sr-only">{label || tooltip}</span>
    </Button>
  );

  if (tooltip) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>
            <p>{tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return button;
};

// =============================================================================
// MessageBranch 分支消息系统
// =============================================================================

/**
 * 【功能说明】
 * 实现 AI 回答的多版本管理，类似 Git 分支切换
 *
 * 【使用场景】
 * 1. 用户对同一问题点击"重新生成"，产生多个回答版本
 * 2. 用户想对比不同模型的回答（GPT-4 vs Claude）
 * 3. 用户回溯到之前的回答继续对话
 *
 * 【状态管理】
 * 使用 React Context 在组件树中共享分支状态
 * 避免 props drilling，子组件可以通过 useMessageBranch() 访问状态
 *
 * 【类比理解】
 * 就像浏览器的标签页管理：
 * - branches = 所有打开的标签页
 * - currentBranch = 当前激活的标签页索引
 * - goToPrevious/goToNext = 切换到上一个/下一个标签
 */

/**
 * 分支上下文类型定义
 */
type MessageBranchContextType = {
  currentBranch: number;           // 当前显示的分支索引
  totalBranches: number;           // 总分支数
  goToPrevious: () => void;        // 切换到上一个分支
  goToNext: () => void;            // 切换到下一个分支
  branches: ReactElement[];        // 所有分支内容
  setBranches: (branches: ReactElement[]) => void;  // 更新分支列表
};

/**
 * 创建分支上下文
 * null 作为默认值，用于检测是否在 Provider 外部使用
 */
const MessageBranchContext = createContext<MessageBranchContextType | null>(
  null,
);

/**
 * 使用分支上下文的 Hook
 *
 * 【设计模式】
 * 这是"自定义 Hook + Context"模式的标准实现
 * 封装 useContext 调用，提供友好的错误提示
 *
 * 【错误处理】
 * 如果组件在 MessageBranchProvider 外部使用，抛出明确错误
 * 帮助开发者快速定位问题
 */
const useMessageBranch = () => {
  const context = useContext(MessageBranchContext);

  if (!context) {
    throw new Error(
      "MessageBranch 子组件必须在 MessageBranch 组件内部使用。\n" +
      "请确保组件被包裹在 <MessageBranch>...</MessageBranch> 中"
    );
  }

  return context;
};

export type MessageBranchProps = HTMLAttributes<HTMLDivElement> & {
  defaultBranch?: number;           // 默认显示的分支索引
  onBranchChange?: (branchIndex: number) => void;  // 分支切换回调
};

/**
 * 消息分支容器组件
 *
 * 【核心职责】
 * 提供分支状态管理和上下文，包裹所有分支相关内容
 *
 * 【状态设计】
 * - currentBranch: 当前显示的分支（受控/非受控混合模式）
 * - branches: 从子组件收集的分支内容
 *
 * 【导航逻辑】
 * - 上一个：到开头后循环到最后（像轮播图）
 * - 下一个：到最后后循环到开头
 *
 * 【复合组件模式】
 * 配合 MessageBranchContent、MessageBranchSelector 等子组件使用：
 * <MessageBranch defaultBranch={0} onBranchChange={handleChange}>
 *   <MessageBranchContent>
 *     <div>回答版本 1</div>
 *     <div>回答版本 2</div>
 *   </MessageBranchContent>
 *   <MessageBranchSelector />
 * </MessageBranch>
 */
export const MessageBranch = ({
  defaultBranch = 0,
  onBranchChange,
  className,
  ...props
}: MessageBranchProps) => {
  // 当前激活的分支索引
  const [currentBranch, setCurrentBranch] = useState(defaultBranch);
  // 所有分支内容（由 MessageBranchContent 子组件填充）
  const [branches, setBranches] = useState<ReactElement[]>([]);

  // 处理分支切换
  const handleBranchChange = (newBranch: number) => {
    setCurrentBranch(newBranch);
    onBranchChange?.(newBranch);  // 通知父组件
  };

  // 切换到上一个分支（循环）
  const goToPrevious = () => {
    const newBranch =
      currentBranch > 0 ? currentBranch - 1 : branches.length - 1;
    handleBranchChange(newBranch);
  };

  // 切换到下一个分支（循环）
  const goToNext = () => {
    const newBranch =
      currentBranch < branches.length - 1 ? currentBranch + 1 : 0;
    handleBranchChange(newBranch);
  };

  // 组装上下文值
  const contextValue: MessageBranchContextType = {
    currentBranch,
    totalBranches: branches.length,
    goToPrevious,
    goToNext,
    branches,
    setBranches,
  };

  return (
    <MessageBranchContext.Provider value={contextValue}>
      <div
        className={cn("grid w-full gap-2 [&>div]:pb-0", className)}
        {...props}
      />
    </MessageBranchContext.Provider>
  );
};

// =============================================================================
// MessageBranchContent 分支内容组件
// =============================================================================

export type MessageBranchContentProps = HTMLAttributes<HTMLDivElement>;

/**
 * 分支内容组件
 *
 * 【核心职责】
 * 1. 收集所有子元素作为分支内容
 * 2. 只显示当前激活的分支，隐藏其他分支
 * 3. 将分支信息同步到 Context
 *
 * 【渲染策略】
 * - 当前分支：display: block
 * - 其他分支：display: hidden
 * 使用 CSS 显示/隐藏而非条件渲染，保持组件状态
 *
 * 【Children 处理】
 * React.Children 可能是单个元素或数组，统一转为数组处理
 * const childrenArray = Children.toArray(children)
 *
 * 【类比理解】
 * 就像 Tabs 组件的 TabPanels：
 * <Tabs>
 *   <TabPanel>内容 1</TabPanel>  ← 当前激活，显示
 *   <TabPanel>内容 2</TabPanel>  ← 隐藏
 * </Tabs>
 */
export const MessageBranchContent = ({
  children,
  ...props
}: MessageBranchContentProps) => {
  const { currentBranch, setBranches, branches } = useMessageBranch();

  // 确保 children 是数组（处理单个子元素的情况）
  const childrenArray = Array.isArray(children) ? children : [children];

  // 同步分支内容到 Context
  // 当子元素变化时，更新全局的分支列表
  useEffect(() => {
    if (branches.length !== childrenArray.length) {
      setBranches(childrenArray);
    }
  }, [childrenArray, branches, setBranches]);

  // 渲染所有分支，但只有当前分支可见
  return childrenArray.map((branch, index) => (
    <div
      className={cn(
        "grid gap-2 overflow-hidden [&>div]:pb-0",
        // 根据当前分支索引控制显示/隐藏
        index === currentBranch ? "block" : "hidden",
      )}
      key={branch.key}  // 使用 React 元素的 key 作为唯一标识
      {...props}
    >
      {branch}
    </div>
  ));
};

export type MessageBranchSelectorProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage["role"];
};

export const MessageBranchSelector = ({
  className,
  from,
  ...props
}: MessageBranchSelectorProps) => {
  const { totalBranches } = useMessageBranch();

  // Don't render if there's only one branch
  if (totalBranches <= 1) {
    return null;
  }

  return (
    <ButtonGroup
      className="[&>*:not(:first-child)]:rounded-l-md [&>*:not(:last-child)]:rounded-r-md"
      orientation="horizontal"
      {...props}
    />
  );
};

export type MessageBranchPreviousProps = ComponentProps<typeof Button>;

export const MessageBranchPrevious = ({
  children,
  ...props
}: MessageBranchPreviousProps) => {
  const { goToPrevious, totalBranches } = useMessageBranch();

  return (
    <Button
      aria-label="Previous branch"
      disabled={totalBranches <= 1}
      onClick={goToPrevious}
      size="icon-sm"
      type="button"
      variant="ghost"
      {...props}
    >
      {children ?? <ChevronLeftIcon size={14} />}
    </Button>
  );
};

export type MessageBranchNextProps = ComponentProps<typeof Button>;

export const MessageBranchNext = ({
  children,
  className,
  ...props
}: MessageBranchNextProps) => {
  const { goToNext, totalBranches } = useMessageBranch();

  return (
    <Button
      aria-label="Next branch"
      disabled={totalBranches <= 1}
      onClick={goToNext}
      size="icon-sm"
      type="button"
      variant="ghost"
      {...props}
    >
      {children ?? <ChevronRightIcon size={14} />}
    </Button>
  );
};

export type MessageBranchPageProps = HTMLAttributes<HTMLSpanElement>;

export const MessageBranchPage = ({
  className,
  ...props
}: MessageBranchPageProps) => {
  const { currentBranch, totalBranches } = useMessageBranch();

  return (
    <ButtonGroupText
      className={cn(
        "text-muted-foreground border-none bg-transparent shadow-none",
        className,
      )}
      {...props}
    >
      {currentBranch + 1} of {totalBranches}
    </ButtonGroupText>
  );
};

export type MessageResponseProps = ComponentProps<typeof Streamdown>;

export const MessageResponse = memo(
  ({ className, ...props }: MessageResponseProps) => (
    <Streamdown
      className={cn(
        "size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
        className,
      )}
      {...props}
    />
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children,
);

MessageResponse.displayName = "MessageResponse";

export type MessageAttachmentProps = HTMLAttributes<HTMLDivElement> & {
  data: FileUIPart;
  className?: string;
  onRemove?: () => void;
};

export function MessageAttachment({
  data,
  className,
  onRemove,
  ...props
}: MessageAttachmentProps) {
  const filename = data.filename || "";
  const mediaType =
    data.mediaType?.startsWith("image/") && data.url ? "image" : "file";
  const isImage = mediaType === "image";
  const attachmentLabel = filename || (isImage ? "Image" : "Attachment");

  return (
    <div
      className={cn(
        "group relative size-24 overflow-hidden rounded-lg",
        className,
      )}
      {...props}
    >
      {isImage ? (
        <>
          <img
            alt={filename || "attachment"}
            className="size-full object-cover"
            height={100}
            src={data.url}
            width={100}
          />
          {onRemove && (
            <Button
              aria-label="Remove attachment"
              className="bg-background/80 hover:bg-background absolute top-2 right-2 size-6 rounded-full p-0 opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100 [&>svg]:size-3"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              type="button"
              variant="ghost"
            >
              <XIcon />
              <span className="sr-only">Remove</span>
            </Button>
          )}
        </>
      ) : (
        <>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="bg-muted text-muted-foreground flex size-full shrink-0 items-center justify-center rounded-lg">
                <PaperclipIcon className="size-4" />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>{attachmentLabel}</p>
            </TooltipContent>
          </Tooltip>
          {onRemove && (
            <Button
              aria-label="Remove attachment"
              className="hover:bg-accent size-6 shrink-0 rounded-full p-0 opacity-0 transition-opacity group-hover:opacity-100 [&>svg]:size-3"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              type="button"
              variant="ghost"
            >
              <XIcon />
              <span className="sr-only">Remove</span>
            </Button>
          )}
        </>
      )}
    </div>
  );
}

export type MessageAttachmentsProps = ComponentProps<"div">;

export function MessageAttachments({
  children,
  className,
  ...props
}: MessageAttachmentsProps) {
  if (!children) {
    return null;
  }

  return (
    <div
      className={cn(
        "ml-auto flex w-fit flex-wrap items-start gap-2",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export type MessageToolbarProps = ComponentProps<"div">;

export const MessageToolbar = ({
  className,
  children,
  ...props
}: MessageToolbarProps) => (
  <div
    className={cn(
      "mt-4 flex w-full items-center justify-between gap-4",
      className,
    )}
    {...props}
  >
    {children}
  </div>
);
