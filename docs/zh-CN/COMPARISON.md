# 同类评分对比

这不是“谁更高级”的通用排名，而是围绕一个具体场景评分：

> 已经有自己的 VPS，尤其是住宅 IP VPS；想部署自用 VLESS Reality；希望新手能照文档落地；后续维护成本低；最好能处理 Telegram / Discord 对住宅 IP 软降权的问题。

如果你要做多用户商业面板、计费、到期管理，3x-ui / x-ui 这类项目会更合适。如果你只是要一个自用、可审计、低暴露面的住宅 IP 节点，`reality-resi-stack` 的取舍更直接。

## 总分

评分范围 1-5，分数越高表示越适合“住宅 IP 自托管 VLESS Reality + 新手可落地 + 低维护”这个场景。

| 方案 | 总分 | 最适合的用户 | 核心取舍 |
|---|---:|---|---|
| reality-resi-stack | 4.7 | 自用住宅 IP / 小团队 / AI 工具用户 | 范围窄、部署快、住宅 IP 场景强，不做多用户面板 |
| 3x-ui | 3.8 | 需要 Web 面板、多协议、多用户管理的人 | 功能丰富，但面板和数据库带来更高运维面 |
| x-ui | 3.5 | 想用 Xray 面板快速管理多协议的人 | 面板能力强，自用住宅 IP 分流不是默认重点 |
| 手写 Xray/sing-box 配置 | 3.2 | 熟悉协议和配置的人 | 最灵活，但新手成本最高 |
| 商业机场/代理面板 | 2.8 | 不想自管服务器的人 | 省事，但不可审计，住宅 IP 出口不可控 |

## 维度评分

| 维度 | reality-resi-stack | 3x-ui | x-ui | 手写配置 | 商业服务 |
|---|---:|---:|---:|---:|---:|
| 住宅 IP 场景适配 | 5 | 3 | 3 | 4 | 2 |
| 新手部署简单度 | 5 | 4 | 4 | 1 | 5 |
| 订阅 URL / 流量卡片 | 4 | 4 | 4 | 1 | 4 |
| Telegram / Discord 分流 | 5 | 3 | 3 | 4 | 2 |
| 安全默认值 | 4 | 3 | 3 | 2 | 2 |
| 可审计性 | 5 | 3 | 3 | 5 | 1 |
| 运维复杂度 | 4 | 3 | 3 | 2 | 5 |
| 多用户 / 面板能力 | 1 | 5 | 5 | 2 | 4 |

## 为什么 reality-resi-stack 在这个场景更强

### 1. 它默认承认“住宅 IP 是资产”

很多通用安装器和面板默认服务的是“便宜 VPS 翻墙”场景，重点是多协议、多用户、面板管理。`reality-resi-stack` 的默认前提不同：住宅 IP 的价值在于出口信誉，所以应该优先给 OpenAI、Anthropic、Netflix、银行等服务使用。

### 2. 它把 Telegram / Discord 慢当成一等问题

住宅 IP 段可能被即时通讯服务软降权，常见表现是 Telegram 发文件卡死、Discord 语音质量差。本项目的双节点模式直接给出路径：OpenAI / Claude 走住宅节点，Telegram / Discord 走数据中心节点，客户端仍然只订阅一份配置。

### 3. 它没有 Web 面板暴露面

3x-ui / x-ui 的优势是 Web 管理和多用户能力，但 Web 面板也意味着额外登录入口、数据库、面板升级和访问控制。本项目默认通过 Bash + systemd + 文件配置完成部署，适合单用户和小团队自用。

### 4. 它更适合可重复部署

安装器支持 `--dry-run`、`--config`、`--non-interactive` 和幂等重跑。你可以先看它会做什么，再正式执行；也可以把变量放进配置文件，后续复制到新机器。

### 5. 它内置基础运维边界

默认处理 systemd 服务、UFW / fail2ban、BBR、swap、journald 限额、每日配置备份、`/healthz` 和 `Subscription-Userinfo`。这不是“更高级”，而是新手最容易漏掉的维护面。

## 什么时候不该选它

不要为了所有场景都选 `reality-resi-stack`：

- 你要给很多用户开账号、限速、设置到期时间：选 3x-ui / x-ui。
- 你需要 Web UI 每天管理入站、出站和用户：选面板。
- 你想学习每一个 sing-box / Xray 字段：从官方文档和手写配置开始。
- 你不想维护服务器、不想碰 SSH：买商业服务更省事。
- 你需要 Kubernetes / Docker Compose / 多租户企业平台：这不是本项目范围。

## 依据与边界

对比依据来自公开项目说明和官方文档：

- [3x-ui README](https://github.com/MHSanaei/3x-ui)：Web-based Xray-core control panel、多协议、多用户、流量/到期/IP 限制、一行安装。
- [x-ui README](https://github.com/sing-web/x-ui)：Xray 面板、多协议、多入站/客户端、流量状态、订阅和 API 能力。
- [Project X 官方文档](https://xtls.github.io/)：VLESS、XTLS、REALITY 和 routing 是 Xray 生态的核心能力。
- [sing-box route 文档](https://sing-box.sagernet.org/configuration/route/)：route 规则支持按域名、IP、端口、协议等维度把连接送到不同 outbound。

这些来源只用于能力边界和场景对比。评分是面向本项目目标用户的产品判断，不代表通用技术优劣。

## 下一步

- 第一次部署：先看 [新手完整教程](BEGINNER_GUIDE.md)
- 已经会 SSH：直接看 [部署指南](DEPLOYMENT.md)
- 要导入客户端：看 [客户端导入](CLIENTS.md)
- TG / Discord 慢：看 [双节点 + 智能分流](DUAL-NODE.md)
