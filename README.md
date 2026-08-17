# ChatDog

> 一个极简的 **Windows 局域网聊天工具** —— 无需服务器、无需联网、无需安装，同一 WiFi / 热点下的同学即开即聊。

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)
![UI](https://img.shields.io/badge/UI-Tkinter-orange)

---

## ✨ 特性

- **零配置局域网聊天**：基于 UDP 广播 + 单播双通道，连上同一个 WiFi / 手机热点就能互相发消息，不需要服务器、不需要注册。
- **可靠的投递机制**：消息会同时通过广播和点对点单播发送，即使路由器丢弃广播，适合课堂紧急通知。
- **快捷消息**：内置 `Ctrl+2` ~ `Ctrl+0` 快捷短语（收到 / 好的 / 稍等……），支持自定义。
- **桌面通知**：收到新消息时右下角弹出悬浮通知，5 秒自动淡出。
- **上线/下线提醒**：用户加入或离开聊天室时自动广播系统消息。
- **自动放行防火墙**：以管理员身份运行时自动添加 UDP 端口放行规则，无需手动配置。
- **单文件绿色版**：提供打包好的 `chatdog.exe`，双击即用，无需安装 Python。

## 📸 使用场景

- 断网环境下的沟通交流

## 🚀 快速开始

### 方式一：直接运行 exe（推荐）

1. 从 [Releases](https://github.com/huangjiaquqi/ChatDog/releases) 或仓库 `dist/chatdog.exe` 下载可执行文件
2. 双击运行，输入昵称即可加入聊天
3. 让同一局域网内的其他同学也运行 ChatDog
**注意，您只需要把这个exe独立拷贝出来，无需文件夹即可随地运行**

### 方式二：从源码运行

```bash
# 需要 Python 3.8+（自带 Tkinter）
git clone https://github.com/huangjiaquqi/ChatDog.git
cd ChatDog
python chatdog.py
```

### 自行打包 exe

```bash
pip install pyinstaller
pyinstaller chatdog.spec
# 产物位于 dist/chatdog.exe
```

## ⌨️ 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Enter` | 发送输入框中的消息 |
| `Ctrl+1` | 发送紧急警告（全员红色闪烁弹窗） |
| `Ctrl+2` ~ `Ctrl+0` | 发送对应的快捷消息（可自定义） |

## 🔧 工作原理

```
┌──────────┐   UDP 广播 (发现彼此)    ┌──────────┐
│  用户 A   │ ──────────────────────▶ │  用户 B   │
│          │ ◀────────────────────── │          │
└──────────┘                          └──────────┘
      ▲                                     ▲
      │      UDP 单播 (定向投递消息)          │
      └─────────────────────────────────────┘
```

1. **在线发现**：每个客户端每 3 秒广播一次心跳，其他客户端收到后记住对方的 IP 地址。
2. **消息投递**：发送消息时同时走 **广播**（发现新上线用户）和 **单播**（定向发给每个已知在线用户），双保险确保消息不丢。
3. **消息去重**：每条消息带唯一 `msg_uid`，广播与单播重复到达时只显示一次。
4. **默认端口**：UDP `50007`，所有客户端保持一致。

## ❓ 常见问题

**Q: 为什么收不到别人的消息？**
A: 请确认所有设备连接在**同一个 WiFi / 热点**下，且路由器没有开启"AP 隔离 / 客户端隔离"。如果以管理员身份运行，程序会自动放行防火墙；否则请手动在 Windows 防火墙中放行 UDP 50007 端口。

**Q: 能跨网段 / 跨路由器使用吗？**
A: 不能。ChatDog 基于局域网广播与单播，仅限同一二层局域网内使用。

**Q: 消息会加密吗？**
A: 不会。消息以明文 JSON 在局域网内传输，仅适用于可信的局域网环境。

## 📁 项目结构

```
ChatDog/
├── chatdog.py        # 主程序（单文件实现全部功能）
├── chatdog.spec      # PyInstaller 打包配置
├── icon.ico          # 应用图标
├── dist/chatdog.exe  # 打包好的可执行文件
└── README.md
```

## 📜 License

[MIT](https://opensource.org/licenses/MIT)
