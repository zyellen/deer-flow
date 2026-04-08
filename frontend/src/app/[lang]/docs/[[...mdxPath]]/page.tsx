import { generateStaticParamsFor, importPage } from "nextra/pages";

import { useMDXComponents as getMDXComponents } from "../../../../mdx-components";

// 预生成所有文档路由参数，提升静态站点访问性能。
export const generateStaticParams = generateStaticParamsFor("mdxPath");

// 动态读取 MDX 元信息并注入页面 metadata（标题、描述等）。
export async function generateMetadata(props) {
  const params = await props.params;
  const { metadata } = await importPage(params.mdxPath, params.lang);
  return metadata;
}

// 特殊处理说明：wrapper 是从组件映射对象上取出的函数引用。
// 这里保留原始引用方式，避免额外包装导致类型推断与运行时行为不一致。
// eslint-disable-next-line @typescript-eslint/unbound-method
const Wrapper = getMDXComponents().wrapper;

// 文档页面主渲染流程：加载 MDX 内容 + 目录 + 元信息，再交给统一 Wrapper 排版。
// 学习提示：可类比 Vue 的“布局组件 + <router-view>”，Wrapper 相当于外层布局壳。
export default async function Page(props) {
  const params = await props.params;
  const {
    default: MDXContent,
    toc,
    metadata,
    sourceCode,
  } = await importPage(params.mdxPath, params.lang);
  return (
    <Wrapper toc={toc} metadata={metadata} sourceCode={sourceCode}>
      <MDXContent {...props} params={params} />
    </Wrapper>
  );
}
