# 故障排查 | Troubleshooting

按"症状 → 最常见原因 → 修复"顺序排列。诊断永远是先看几个基础状态：

```bash
systemctl status sing-box --no-pager
journalctl -u sing-box -n 50 --no-pager
ss -tlnp | grep ':443'
ufw status verbose
sing-box check -C /etc/sing-box/conf
```

任何 issue 模板都会让你先粘贴这几条的输出。

---

## 客户端连不上

| 可能原因 | 排查 |
|---|---|
| 云厂商安全组没放 `443/tcp` | 登入控制台检查安全组 |
| UFW 没放 `443/tcp` | `ufw status` |
| 客户端 UUID 不一致 | 比对客户端 vless:// 链接里的 UUID 与服务端 `secrets.env` |
| 客户端 `public-key` 填错 | 比对客户端 `pbk=` 与服务端的 `REALITY_PUBLIC_KEY` |
| 客户端 `servername` 与服务端 `server_name` 不一致 | 都应该是同一个 SNI（如 `addons.mozilla.org`） |
| 客户端不支持 Reality 或 `xtls-rprx-vision` | 用最新版 v2rayN / Clash Verge / sing-box |
| 服务器已有 nginx/caddy/apache 占 443 | `ss -tlnp \| grep 443` 看占用进程 |
| sing-box 配置有错 | `sing-box check -C /etc/sing-box/conf` |

---

## TG / Discord 上传卡死、语音卡顿

这是**最常见的"住宅 IP 软风控"**症状，**不是协议问题**。

**症状判定：**
- 客户端测速能跑满
- 普通文字消息正常
- 大文件、语音、视频上传质量明显下降
- 同一账号在原生网络下没事

**根因：** 你的住宅 IP 所在 /24 子网历史上有人跑过 bot，Telegram/Discord 的反滥用系统已经把整段 IP 信誉降级 —— 这跟你这个具体账号无关，纯粹是连坐。

**解决方案：** 双节点 + 智能分流（按域名把 TG/Discord 走数据中心节点）。详见 [DUAL-NODE.md](DUAL-NODE.md)。

**临时方案**（不动服务端，5 分钟）：在客户端 Clash YAML 加一段路由规则，把 TG/Discord 流量丢给一个非住宅 IP 的备用代理（哪怕是另一个普通机场）。规则示例：

```yaml
rules:
  - DOMAIN-SUFFIX,telegram.org,你的备用节点名
  - DOMAIN-SUFFIX,t.me,你的备用节点名
  - DOMAIN-SUFFIX,discord.com,你的备用节点名
  - IP-CIDR,91.108.4.0/22,你的备用节点名,no-resolve
  - IP-CIDR,91.108.16.0/22,你的备用节点名,no-resolve
  - IP-CIDR,149.154.160.0/20,你的备用节点名,no-resolve
  # 其它走默认 PROXY
```

---

## 订阅 URL 能打开，但客户端不显示流量卡片

```bash
curl -I http://你的服务器IP/你的token
```

必须看到这几个响应头：

- `Subscription-Userinfo`
- `Profile-Title`
- `Profile-Update-Interval`

如果都有，但客户端不显示 → 是**客户端版本不支持**这个卡片渲染（v2rayN 4.x 之前、某些 Clash 移动端），不影响代理本身。换支持的客户端即可。

如果响应头缺失 → 检查 `subscription-leaf.service` 日志：

```bash
journalctl -u subscription-leaf -n 50 --no-pager
```

---

## 流量统计与商家后台对不上

**短答：** 这是**预期行为**，不是 bug。

**长答：** 订阅服务统计的是 `/sys/class/net/<iface>/statistics/rx_bytes + tx_bytes` 的月累计差值。商家计费可能：

- 按出方向计费（你的 tx_bytes 而不是 rx + tx）
- 按 95 百分位计费（不是累加）
- 按五分钟峰值计费
- 加上控制层流量（DHCP / ARP / 你自己 SSH 进去看的流量）
- 月初零点对不上你订阅服务初次落盘的时间

**校准方法**（让订阅卡片从这一刻起跟商家后台对齐）：

```bash
CURRENT_TOTAL=$(( $(cat /sys/class/net/eth0/statistics/rx_bytes) + $(cat /sys/class/net/eth0/statistics/tx_bytes) ))
STATE_USED=$(python3 -c "import json; print(int(json.load(open('/var/lib/reality-resi-stack/usage-state.json'))['used_bytes']))")
BACKEND_USED=900000000000   # 替换成商家后台显示的本月已用字节数

OFFSET=$((BACKEND_USED - STATE_USED))
sudo sed -i "s/^USAGE_OFFSET_BYTES=.*/USAGE_OFFSET_BYTES=${OFFSET}/" /etc/reality-resi-stack/subscription-leaf.env
sudo systemctl restart subscription-leaf
```

如果 `usage-state.json` 还不存在或刚被恢复清空，先访问一次 `http://127.0.0.1/<TOKEN>/status` 让 leaf 建立 baseline，再按上面公式校准。`USAGE_OFFSET_BYTES` 可以为负数；服务端会把最终返回值钳到不低于 0。

---

## TLS 自握手失败 / Reality 似乎没生效

```bash
echo | openssl s_client -connect 127.0.0.1:443 -servername addons.mozilla.org 2>/dev/null | grep subject=
```

应该返回 `addons.mozilla.org` 的证书 subject。如果返回别的（比如 sing-box 的自签证书 / `cannot connect`）：

- **没装 sing-box / 没启动**：`systemctl status sing-box`
- **SNI 配错**：检查 `/etc/sing-box/conf/11_xtls-reality_inbounds.json` 的 `tls.server_name` 和 `reality.handshake.server` 必须**完全一致**
- **服务器到 SNI 站的握手网络出问题**：服务器自己 `curl -v https://addons.mozilla.org/` 看能不能成
- **Reality 私钥与客户端公钥不匹配**：在服务器重新跑 `sing-box generate reality-keypair` 获取一对，更新服务端 `private_key` 和客户端 `public-key`

---

## fail2ban 把我自己锁了

```bash
fail2ban-client status sshd                   # 看被封 IP
fail2ban-client set sshd unbanip 1.2.3.4      # 解封
```

预防：在 `--harden-ssh` 之前确保有备用 SSH 会话；fail2ban 默认 5 次失败封 1 小时。

---

## 升级 sing-box 后服务起不来

```bash
journalctl -u sing-box -n 100 --no-pager
sing-box check -C /etc/sing-box/conf
```

最常见原因：新版 sing-box 改了 schema。把错误信息搜 [sing-box 官方 changelog](https://github.com/SagerNet/sing-box/releases)。短期处理：

```bash
apt-get install -y sing-box=<上一个能跑的版本号>
apt-mark hold sing-box   # 暂时不让 apt 升级
```

再到 reality-resi-stack 这边开 issue。

---

## NTP 时间同步失败

```bash
timedatectl
chronyc sources -v
```

多个 NTP 源 `Reach=0` 通常是 VPS 厂商封了 `123/UDP` 出站。这**不阻塞代理转发**（VLESS 不依赖时钟严格同步），但会让日志时间戳错乱。可以换到 NTS（TLS 化的 NTP）：

```bash
sudo sed -i 's|^pool .*|pool time.cloudflare.com iburst nts|' /etc/chrony/chrony.conf
sudo systemctl restart chrony
```

---

## 配置改坏 / 想回滚

```bash
ls /var/backups/reality-resi-stack/
# 选一个时间戳较新的
tar -tzf /var/backups/reality-resi-stack/reality-resi-stack-2026-05-17-120000.tar.gz | head
```

恢复（先停服务）：

```bash
systemctl stop sing-box
tar -xzf /var/backups/reality-resi-stack/reality-resi-stack-XXXX.tar.gz -C /
systemctl daemon-reload
systemctl start sing-box
sing-box check -C /etc/sing-box/conf
```

⚠️ 备份归档**不含** `var/lib/reality-resi-stack/usage-state.json` 或 `usage-cache.json`（运行时数据），所以恢复后流量计数会从恢复时刻重新起算。归档会包含 `/etc/reality-resi-stack/`，里面有密钥和 token，不能公开传播。恢复后可以用上面"流量统计漂移"小节的命令补一个 offset。

---

## 出口 IP 不是预期的住宅 IP

```bash
curl --proxy socks5h://127.0.0.1:7891 https://ipinfo.io
```

如果返回的 IP 不是你的住宅 IP：

- 客户端规则可能把请求走了另一个节点 → 看客户端规则匹配日志
- DNS 污染：客户端没有用 SNI 嗅探就走了 Direct → 检查 Clash 的 `mode: rule` 与 `dns:` 段
- 你的住宅节点已经挂了，客户端自动 fallback 到了备用节点 → `systemctl status sing-box` on the residential node

---

## 还没解决？

提 issue 时带上：

- `journalctl -u sing-box -n 100 --no-pager`
- `sing-box version`
- `cat /etc/os-release | head -3`
- 期望 vs 实际行为
- **不要** 粘贴 UUID / Reality 公私钥 / 服务器 IP

模板会再提醒一次。
