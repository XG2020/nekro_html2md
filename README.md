# 网页转Markdown（nekro_html2md）

## 概述
访问指定网页链接，清洗 HTML 并可选提取正文，转换为 Markdown 文本直接返回给大模型查看。内置多策略重试与反爬应对，失败时以 Markdown 形式返回可读提示，不中断会话。

## 安装与位置
- 插件目录：`plugins/workdir/nekro_html2md/`
- 主文件：[plugin.py](./plugin.py)
- 导出入口：[__init__.py](./__init__.py)

## 提供的方法
- 方法名：`fetch_html_to_markdown`
- 类型：`SandboxMethodType.AGENT`
- 功能：抓取网页、清洗与正文提取、转换为 Markdown 字符串并返回

### 调用示例
```
/exec fetch_html_to_markdown(url="https://example.com/article")
```

### 返回示例（成功）
```markdown
# 页面标题
- 来源: https://example.com/article

正文第一段...
- 列表项 1
- 列表项 2
```

### 返回示例（失败）
```markdown
# 网页内容整理
- 来源: https://example.com/article

抓取失败
错误: HTTPSConnectionPool(...): Max retries exceeded ...
```

## 参数
- `url`（必填）：目标网页链接，需为 http/https
- `keep_links`（默认 true）：保留超链接
- `remove_scripts`（默认 true）：移除 `script`/`noscript`
- `remove_styles`（默认 true）：移除 `style`/`link`
- `use_readability`（默认 false）：启用 Readability 正文提取
- `collapse_whitespace`（默认 true）：折叠空白与行尾空格
- `max_length`（默认 0）：返回文本最大长度；0 表示不限制

### 反爬与重试相关参数
- `user_agent`：自定义 UA 文本
- `accept_language`：例如 `zh-CN,zh;q=0.9,en;q=0.8`
- `referer`：引用页；默认使用目标 URL
- `retries`（默认 2）：每种策略的最大重试次数
- `backoff_ms`（默认 500）：指数退避基础毫秒
- `delay_ms_min`/`delay_ms_max`（默认 200/1200）：随机延迟范围
- `timeout`（默认 20）：单次请求超时时间秒
- `use_cloudscraper`（默认 true）：是否使用 Cloudscraper 处理 JS 挑战

## 反爬应对策略
- 多策略顺序：
  1. 代理 + Cloudscraper
  2. 直连 + Cloudscraper
  3. 直连 + 普通会话
  4. 代理 + 普通会话
- 随机延迟与指数退避，降低风控触发概率
- 代理失败自动切换直连并重置尝试计数
- 自动轮换常见浏览器 UA
- 所有策略失败时返回 Markdown 提示而非抛异常

### 常用调用
```
/exec fetch_html_to_markdown(
  url="https://example.com/article",
  use_readability=true,
  retries=3,
  backoff_ms=800,
  delay_ms_min=300,
  delay_ms_max=1500,
  user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
  accept_language="zh-CN,zh;q=0.9"
)
```

## 注意事项
- 请遵守网站服务条款与 robots.txt，避免过度抓取与绕过强认证
- 对强 JS 站点优先尝试 `use_cloudscraper=true`；不稳定时切换直连重试
- 对新闻/文章页启用 `use_readability=true` 可显著提升可读性
- 如站点拒绝代理，插件会自动切换直连；也可直接传入默认参数进行直连

