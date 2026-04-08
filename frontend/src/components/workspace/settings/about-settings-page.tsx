"use client";

import { Streamdown } from "streamdown";

import { aboutMarkdown } from "./about-content";

// 关于页：直接渲染内置 Markdown 内容，避免维护重复的静态 JSX。
// 学习提示：这类“数据驱动视图”可类比 Vue 中 `v-html`/Markdown 渲染组件的使用场景。
export function AboutSettingsPage() {
  return <Streamdown>{aboutMarkdown}</Streamdown>;
}
