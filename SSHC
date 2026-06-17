#!/bin/bash

# ====================================================================
# Ubuntu SSH 安全加固与内存清理一键脚本
# ====================================================================

# 确保脚本是以 root 权限运行
if [ "$EUID" -ne 0 ]; then
  echo "❌ 错误: 请使用 sudo 或 root 权限运行此脚本！"
  exit 1
fi

echo "=================================================="
# 1. 备份并生成新的 SSH 配置文件
echo "步骤 1: 正在备份并生成新的 SSH 配置文件..."
SSH_CONFIG="/etc/ssh/sshd_config"

if [ -f "$SSH_CONFIG" ]; then
    cp "$SSH_CONFIG" "${SSH_CONFIG}.bak_$(date +%Y%m%d_%H%M%S)"
    echo "💾 已将原配置备份至 ${SSH_CONFIG}.bak_..."
fi

# 写入完整的安全配置（包含 Include 引用，端口 18222，禁用密码）
cat << 'EOF' > "$SSH_CONFIG"
# ====================================================================
# 安全强化的 SSH 服务配置文件 (Ubuntu) - 包含系统默认 Include 引用
# ====================================================================

# 引入系统自定目录配置（必须保留在顶部）
Include /etc/ssh/sshd_config.d/*.conf

# --------------------------------------------------------------------
# 1. 基础网络与端口设置
# --------------------------------------------------------------------
# 自定义高位端口，彻底消除 99% 的自动化脚本扫描
Port 18222
Protocol 2
AddressFamily inet
ListenAddress 0.0.0.0

# --------------------------------------------------------------------
# 2. 认证与访问控制
# --------------------------------------------------------------------
# 严禁 root 用户直接登录（若需改回密钥登录可设为 prohibit-password）
PermitRootLogin no

# 限制最大认证尝试次数，防止暴力破解
MaxAuthTries 3
MaxSessions 2

# 强制使用公钥认证，彻底禁用密码登录
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no

# 禁用一切不安全的认证方式
HostbasedAuthentication no
IgnoreRhosts yes
KbdInteractiveAuthentication no

# --------------------------------------------------------------------
# 3. 加密、密钥交换与主机密钥 (采用系统默认以保持兼容性)
# --------------------------------------------------------------------
# 此处已移除严格限制。系统将自动支持 Ubuntu 默认的所有常见算法，
# 从而兼容老旧的密钥类型和旧版客户端。

# --------------------------------------------------------------------
# 4. 会话与超时控制
# --------------------------------------------------------------------
# 客户端闲置 5 分钟后自动断开，防止会话被劫持
ClientAliveInterval 300
ClientAliveCountMax 0

# 登录超时时间设置为 30 秒，未及时登录则断开
LoginGraceTime 30

# --------------------------------------------------------------------
# 5. 日志与环境控制
# --------------------------------------------------------------------
LogLevel VERBOSE
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
PermitUserEnvironment no
PrintMotd no
AcceptEnv LANG LC_*

# --------------------------------------------------------------------
# 6. 外部子系统
# --------------------------------------------------------------------
Subsystem sftp internal-sftp
EOF

echo "✅ SSH 配置文件写入成功！"
echo "--------------------------------------------------"

# 2. 配置防火墙放行新端口
echo "步骤 2: 正在检查并配置 UFW 防火墙..."
if command -v ufw >/dev/null 2>&1; then
    ufw allow 18222/tcp
    ufw reload
    echo "✅ 防火墙已成功放行 18222 端口！"
else
    echo "⚠️ 未检测到 UFW 防火墙，请确保你的云安全组已放行 18222 端口！"
fi
echo "--------------------------------------------------"

# 3. 检查 SSH 语法并重启服务
echo "步骤 3: 正在验证并重启 SSH 服务..."
sshd -t
if [ $? -eq 0 ]; then
    echo "⚙️ 语法检查通过，正在重载服务以应用新端口..."
    systemctl daemon-reload
    systemctl restart ssh.socket >/dev/null 2>&1
    systemctl restart ssh
    echo "✅ SSH 服务重启成功！"
else
    echo "❌ 错误: SSH 配置文件语法检查失败，请检查并还原！"
    exit 1
fi
echo "--------------------------------------------------"

# 4. 紧急清理缓存释放内存
echo "步骤 4: 正在清理被暴力破解脚本刷满的日志与内存缓存..."
journalctl --vacuum-time=2d
systemctl restart systemd-journald
systemctl restart rsyslog
sync
sysctl -w vm.drop_caches=3
echo "✅ 内存缓存清理完毕！"

echo "=================================================="
echo "🎉 脚本执行完毕！"
echo "⚠️  重要提醒：请绝对不要关闭当前窗口！"
echo "👉 请立即打开一个新的终端窗口测试：ssh -p 18222 用户名@服务器IP"
echo "=================================================="
