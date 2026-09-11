[中文](#cn-v0.1.5) | [English](#en-v0.1.5)

作为 `0.1.5` 系列的首个正式版本，本版本汇总了自 `v0.1.2` 以来的主要用户和开发者相关变更。

<h3 id="cn-v0.1.5">新增功能</h3>

- DeepSeek 模型适配器新增 `DeepSeek-V41-Flash`（`deepseek-flash`）支持文本、图片及会话历史中的系统提示词更新。 @LegGasai
- Web 支持上传任意类型的通用文件：文件与图片可在同一预览区混排。 @CreatixChu
- 支持动态修改系统提示词且不破坏 KV Cache，模型需显式声明支持。 @tianyicui

### 体验优化

- Web 可直接显示顶层及 PTC 嵌套 `read_image` 的图片结果。 @Chinesezjc, @kermanx
- Windows 上的本地非终端子进程不再弹出控制台窗口。 @turtle1999

### 修复

- 修复 `dsh plugin add` 在部分 Windows 环境下路径解析错误的问题。 @turtle1999

## English

This is the first stable release of the `0.1.5` series. It summarizes the main
user-facing and developer-facing changes since `v0.1.2`.

### New features

- Added `DeepSeek-V41-Flash` support to the DeepSeek model adapter. @LegGasai
- Web can upload arbitrary files. @CreatixChu
