# Domain Seeds（可选）

这个目录放**可选的**领域 seed yaml，给 `dimension_discovery` 子图作为提示。

## 关键原则

- **不填 = 全自动**：系统会通过 web 检索 + LLM 整合自己发现对比维度
- **填了 = seed**：你的 yaml 作为"我想强调这些维度"的钩子，与自动发现的维度取并集

## yaml 模板

```yaml
# 文件名约定: {target_vertical}.yaml（如 office_software.yaml）
vertical: office_software
priority_dimensions:
  - 协同编辑能力
  - 视频会议质量
  - AI 助手
  - 移动端体验
  - 安全合规
trusted_sources:
  - "https://www.feishu.cn"
  - "https://www.dingtalk.com"
forbidden_sources:
  - "*.example-spam.com"
notes: |
  办公软件赛道关键关注移动端 + 国际化
```

## 与 long-term memory 的区别

| | domain_seeds | long-term memory |
|---|---|---|
| 来源 | **人工**填写 | 系统**自学习**积累 |
| 形态 | YAML 文件 | SQLite/向量库 |
| 用途 | 一次性提示 | 跨 session 沉淀 |
| 必需性 | 可选 | 系统持续运行时自动生成 |

不上传到 git 的请放到 `data/private/`，不在这里。
