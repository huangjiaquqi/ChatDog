# ChatDog

> 一个极简的 **Windows 局域网聊天工具** —— 无需服务器、无需联网、无需安装，支持完全无网直连，同一 WiFi / 热点 / 网线下的同学即开即聊。

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)
![UI](https://img.shields.io/badge/UI-CustomTkinter-orange)

---

## 特性

- **三种连接模式，完全无网可用**：
  - 默认模式：同一 WiFi/热点下 UDP 广播+单播自动发现，零配置；
  - 服务器模式：TCP 监听本机端口，其他人直连你的 IP（网线直连、无路由器也能聊）；
  - 客户端模式：TCP 直连对方的 IP 和端口。
- **配置记忆**：历史模式/IP/端口自动保存在程序目录 `chatdog_profiles.json`，启动时一键复用，支持顶置、重命名、删除。
- **可靠的投递机制**：消息双通道投递 + 唯一 `msg_uid` 去重，广播被丢也不怕。
- **昵称内嵌主窗口**：顶栏直接改昵称，自动记忆、广播改名，无独立弹窗。
- **手机式叠层通知**：右下角多条通知堆叠，新通知推入、旧的自动上移；消失时从下向上飞行并快速变小变淡。
- **快捷消息**：内置 `Ctrl+2` ~ `Ctrl+0` 快捷短语（收到 / 好的 / 稍等……），支持自定义。
- **上线/下线提醒**：用户加入或离开聊天室时自动广播系统消息。
- **自动放行防火墙**：以管理员身份运行时自动添加 UDP/TCP 端口放行规则，无需手动配置。
- **双发行方式**：提供单文件绿色版 `chatdog.exe`（双击即用）和 `ChatDog_Setup.exe` 安装程序（中文向导、桌面快捷方式、可卸载）。

## 使用场景

- 断网环境下的沟通交流
- 教室 / 宿舍没有 WiFi，一根网线把两台电脑直连起来也能聊
- 路由器开了 AP 隔离导致广播不通？用服务器/客户端模式点对点直连
- 个人热点必须有网才能开？不需要热点，直连即可

## 快速开始

### 方式一：安装程序（推荐）

1. 从仓库 `dist/ChatDog_Setup.exe` 下载安装程序
2. 双击运行，按中文向导完成安装（自动创建桌面/开始菜单快捷方式）
3. 从快捷方式启动 ChatDog，选择连接模式后进入聊天
4. 让同一局域网内的其他同学也运行 ChatDog

### 方式二：绿色版 exe

1. 从 [Releases](https://github.com/huangjiaquqi/ChatDog/releases) 或仓库 `dist/chatdog.exe` 下载可执行文件
2. 双击运行，选择连接模式即可加入聊天
3. 让同一局域网内的其他同学也运行 ChatDog

**注意，您只需要把这个 exe 独立拷贝出来，无需文件夹即可随地运行**

### 方式三：从源码运行

```bash
# 需要 Python 3.8+，并安装 customtkinter
git clone https://github.com/huangjiaquqi/ChatDog.git
cd ChatDog
pip install customtkinter
python chatdog.py
```

### 自行打包 exe 与安装程序

```bash
pip install pyinstaller
pyinstaller chatdog.spec
# 产物位于 dist/chatdog.exe

# 编译安装程序（需安装 Inno Setup 6）
# 用 Inno Setup 编译 chatdog_setup.iss，产物位于 dist/ChatDog_Setup.exe
```

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Enter` | 发送输入框中的消息 |
| `Ctrl+1` | 发送紧急警告（全员红色闪烁弹窗） |
| `Ctrl+2` ~ `Ctrl+0` | 发送对应的快捷消息（可自定义） |

## 工作原理

```
【默认模式】UDP 广播 + 单播双通道（同一局域网）
┌──────────┐   UDP 广播 (发现彼此)    ┌──────────┐
│  用户 A   │ ──────────────────────▶ │  用户 B   │
│          │ ◀────────────────────── │          │
└──────────┘   UDP 单播 (定向投递)     └──────────┘

【服务器/客户端模式】TCP 直连（完全无网可用）
┌──────────┐                          ┌──────────┐
│ 服务器 A  │ ◀────── TCP 长连接 ─────▶ │ 客户端 B  │
│ (监听端口) │      A 的 IP : 端口       │ (主动连接) │
└──────────┘                          └──────────┘
        ▲ 多个客户端可同时连接，服务器负责转发消息
```

1. **在线发现**：默认模式每 3 秒广播一次心跳；服务器模式由服务器维护在线名单（roster）并广播同步。
2. **消息投递**：默认模式广播+单播双保险；服务器模式客户端 → 服务器 → 转发其他所有客户端。
3. **消息去重**：每条消息带唯一 `msg_uid`，多路径重复到达时只显示一次。
4. **默认端口**：UDP `50007`（默认模式），TCP `50008`（服务器/客户端模式，可自定义）。
5. **断线重连**：客户端模式与服务器断开后每 3 秒自动重连。

## 常见问题

**Q: 为什么收不到别人的消息？**
A: 默认模式请确认所有设备连接在**同一个 WiFi / 热点**下，且路由器没有开启"AP 隔离 / 客户端隔离"。如果以管理员身份运行，程序会自动放行防火墙；否则请手动在 Windows 防火墙中放行 UDP 50007 端口。隔离无法解除时，改用**服务器/客户端模式**直连即可。

**Q: 完全没有网络（没有 WiFi、没有热点）能用吗？**
A: 能。用一根网线把两台电脑直连（或通过交换机），一台选**服务器模式**，另一台选**客户端模式**填入对方 IP 直连，全程不需要互联网。

**Q: 配置会保存吗？**
A: 会。每次使用的模式/IP/端口自动存入程序目录的 `chatdog_profiles.json`，下次启动在"历史配置"区一键复用，还能顶置、重命名、删除。

**Q: 为什么本机有好几个 IP？**
A: 每块联网硬件（WiFi 网卡、网线口、VPN 虚拟网卡等）都会分到各自的 IP。告诉对方 IP 时，选你们实际连接方式对应的那个：连同一个 WiFi 就给 WiFi 的 IP，网线直连就给网线网卡的 IP。

**Q: 能跨网段 / 跨路由器使用吗？**
A: 不能。ChatDog 基于局域网广播与单播，仅限同一二层局域网内使用。

**Q: 消息会加密吗？**
A: 不会。消息以明文 JSON 在局域网内传输，仅适用于可信的局域网环境。

## 项目结构

```
ChatDog/
├── chatdog.py                    # 主程序（单文件实现全部功能）
├── chatdog.spec                  # PyInstaller 打包配置
├── chatdog_setup.iss             # Inno Setup 安装程序脚本
├── ChineseSimplified.isl          # Inno Setup 简体中文语言包
├── icon.ico                       # 应用图标
├── chatdog_profiles.json         # 运行时生成：连接配置记忆（模式/IP/端口/昵称）
├── dist/chatdog.exe              # 打包好的可执行文件（绿色版）
├── dist/ChatDog_Setup.exe        # 打包好的安装程序
└── README.md
```

## License

[MIT](https://opensource.org/licenses/MIT)
