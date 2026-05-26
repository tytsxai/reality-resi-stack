# 部署 | Deployment

本文档讲清楚从一台空白 Ubuntu/Debian VPS 到 VLESS+Reality 节点上线的完整流程。两种走法：

- **快速路径**：一行 `bash <(curl ...)` 调用 `install/install.sh`，由它自动完成全部步骤。适合 99% 的情况。
- **手动路径**：把 `install/lib/*.sh` 里的命令逐节贴在 shell 里执行。适合想理解每一步在做什么的人，或在受限网络里需要插队的人。

两种走法产出的服务器**完全等价**。

---

## 1. 前置条件

### 服务器

- 系统：Ubuntu 22.04+ / 24.04 LTS，或 Debian 12+
- 权限：root 或 sudo
- 资源：1 vCPU、512 MiB 内存可跑（脚本会再加 2GiB swap）、10GiB 磁盘
- 网络：公网 IPv4，允许开放 `443/tcp`；若使用订阅服务，再开 `80/tcp`

### 本地

- 一台能 SSH 到服务器的机器

### 不需要的东西

- ❌ 域名
- ❌ TLS 证书（Reality 借用真实站点 SNI 握手）
- ❌ Vercel / Cloudflare 等第三方账号

---

## 2. 变量表

部署前先想清楚这些值。脚本支持交互式填空，但把所有值写进一个 `--config` 文件最干净：

| 变量 | 示例 | 说明 |
|---|---|---|
| `NODE_NAME` | `US-Resi-01` | 客户端显示名 |
| `SNI` | `addons.mozilla.org` | Reality 伪装握手站，需真实可访问的 HTTPS 站 |
| `INBOUND_PORT` | `443` | VLESS 服务端口，强烈建议保持 443 |
| `SSH_PORT` | `22` | SSH 端口；若你改过，传入新值让 UFW 放行 |
| `INTERFACE` | `eth0` | 主网卡名，留空让脚本自动检测 |
| `TIMEZONE` | `America/Los_Angeles` | 可选 |
| `TOTAL_BYTES` | `1063004405760` | 套餐配额（字节），仅用于客户端流量卡片显示，留 0 隐藏 |
| `EXPIRE_TS` | `0` | 套餐到期 Unix 时间戳，`0` 表示不显示 |
| `BILLING_CYCLE_DAY` | `1` | 商家流量重置日；每月 11 号重置就填 `11` |
| `USAGE_POLL_INTERVAL_SECONDS` | `60` | 后台流量采样间隔 |
| `WITH_SUBSCRIPTION` | `1` | 是否安装订阅服务（推荐） |
| `WITH_AGGREGATOR` | `0` | 是否安装聚合模式（双节点才用） |
| `HARDEN_SSH` | `0` | 是否启用 SSH key-only + 改端口（默认关，避免锁服） |

下面所有命令都假设你已经 `export` 了这些变量。

---

## 3. 快速路径：一行安装

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/tytsxai/reality-resi-stack/main/install/install.sh) \
  --node-name "US-Resi-01" \
  --sni addons.mozilla.org \
  --with-subscription
```

脚本会自己 clone 仓库到 `/opt/reality-resi-stack/`，再 exec 完整安装器。所有阶段都在屏幕上有进度。

默认拉取 `main`。如果你要固定某个分支或 tag，先到 [Releases](https://github.com/tytsxai/reality-resi-stack/releases) 选一个已发布 tag，再用：

```bash
REALITY_RESI_STACK_REF=<tag-or-branch> bash <(curl -fsSL https://raw.githubusercontent.com/tytsxai/reality-resi-stack/main/install/install.sh) \
  --node-name "US-Resi-01" \
  --with-subscription
```

**强烈建议先跑一次 `--dry-run`**：

```bash
bash <(curl -fsSL .../install.sh) --node-name "US-Resi-01" --dry-run
```

`--dry-run` 模式下脚本只**打印**会执行的命令，不动任何系统状态。看一遍输出，确认你能接受每一步再去掉 `--dry-run`。

### 用 `--config` 文件（更适合自动化）

```bash
cat > /root/install.env <<'EOF'
NODE_NAME=US-Resi-01
SNI=addons.mozilla.org
INBOUND_PORT=443
INTERFACE=eth0
TIMEZONE=America/Los_Angeles
TOTAL_BYTES=1063004405760
EXPIRE_TS=0
BILLING_CYCLE_DAY=1
USAGE_POLL_INTERVAL_SECONDS=60
WITH_SUBSCRIPTION=1
EOF

bash <(curl -fsSL .../install.sh) --config /root/install.env --non-interactive
```

---

## 4. 手动路径：按 phase 逐节执行

如果你想看每一步在做什么、或在自定义环境里只想跑某几个阶段，可以 clone 仓库后直接 source 库文件再调用对应 phase 函数：

```bash
git clone --depth 1 https://github.com/tytsxai/reality-resi-stack.git /opt/reality-resi-stack
cd /opt/reality-resi-stack
export REPO_ROOT="$PWD" COMMON_SH_LOADED=1
. install/lib/common.sh
. install/lib/system.sh
. install/lib/singbox.sh

export NODE_NAME=US-Resi-01 SNI=addons.mozilla.org INBOUND_PORT=443 INTERFACE=eth0

phase_preflight        # 系统检查
phase_system_init      # apt 包 + BBR + swap + journald 限额
phase_install_singbox  # 安装 sing-box（含 GPG 指纹校验）
phase_generate_keys    # 生成 UUID + Reality 密钥对 + SUB_TOKEN
phase_configure_singbox  # 渲染 /etc/sing-box/conf/*
phase_singbox_service  # 写 systemd unit + enable --now
phase_firewall         # UFW + fail2ban
phase_verify           # 端到端自检
```

每个 phase 都是独立函数，幂等可重跑。源码在 `install/lib/`。

---

## 5. 验证清单

安装结束时脚本会打印一张"完成卡"，包含 vless:// 链接。手动复查：

```bash
systemctl is-active sing-box                 # 应输出 active
ss -tlnp | grep ':443'                        # 应看到 sing-box 监听
sing-box check -C /etc/sing-box/conf          # 配置合法性
ufw status verbose                            # 防火墙规则
fail2ban-client status sshd                   # SSH 防爆破
sysctl net.ipv4.tcp_congestion_control        # 应输出 bbr
journalctl -u sing-box -n 20 --no-pager       # 启动日志无错误
```

订阅服务（若装了）：

```bash
curl -i http://127.0.0.1/healthz
curl -I http://YOUR_SERVER_IP/$(grep ^SUB_TOKEN /etc/reality-resi-stack/secrets.env | cut -d= -f2)
```

`curl -I` 应看到这几个响应头：

- `Content-Disposition`
- `Profile-Title`
- `Profile-Update-Interval`
- `Subscription-Userinfo`

客户端验证：

- 用订阅 URL 导入到 v2rayN / Clash Verge / sing-box 移动端
- 访问 `https://api.openai.com/v1/models`，未带 API key 时应返回 401，证明 OpenAI 链路可达
- 用 `curl --proxy socks5h://127.0.0.1:7891 https://ipinfo.io` 确认出口 IP 是你的住宅 IP，不是别的

---

## 6. 升级 sing-box 版本

```bash
apt-get update && apt-get install --only-upgrade -y sing-box
systemctl restart sing-box
sing-box version
sing-box check -C /etc/sing-box/conf
```

如果版本不在仓库锁定范围内（仓库 CI 会定期 bump），先看 [CHANGELOG.md](../../CHANGELOG.md) 确认兼容性。

---

## 7. 卸载

```bash
bash /opt/reality-resi-stack/install/uninstall.sh
```

默认保留 `/etc/reality-resi-stack/`（含密钥，不能公开传播）和 `/var/backups/reality-resi-stack/`（备份归档）。要全部清除：

```bash
bash /opt/reality-resi-stack/install/uninstall.sh --purge-all
```

⚠️ `--purge-all` 会删除 UUID 和 Reality 密钥；删除后无法恢复，所有客户端订阅都将作废。

---

## 8. 下一步

- 第一次部署、想按步骤照做 → [BEGINNER_GUIDE.md](BEGINNER_GUIDE.md)
- 客户端怎么导入 → [CLIENTS.md](CLIENTS.md)
- 订阅服务的设计与端点契约 → [SUBSCRIPTION.md](SUBSCRIPTION.md)
- 启用双节点 + 智能分流（解决 TG 软风控等） → [DUAL-NODE.md](DUAL-NODE.md)
- 和 3x-ui / x-ui / 手写配置怎么选 → [COMPARISON.md](COMPARISON.md)
- 跑起来后出问题 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
