# -*- coding: utf-8 -*-
"""ChatDog - 局域网聊天工具（现代化深色 UI 版）"""
import socket
import threading
import json
import customtkinter as ctk
from datetime import datetime
import uuid
import sys
import os
import ctypes
import subprocess
import time

# ============== 配置 ==============
PORT = 50007                 # UDP通信端口（所有客户端必须一致）
BROADCAST_ADDR = '255.255.255.255'  # 受限广播地址（兜底）
PEER_TIMEOUT = 15            # 在线用户超时时间（秒），超过则视为离线
ANNOUNCE_INTERVAL = 3        # 上线广播/心跳间隔（秒）
# =================================

# ---------- 设计令牌 ----------
C_BG       = "#141519"   # 全局背景
C_SURFACE  = "#1c1e24"   # 卡片/控件底
C_SURFACE2 = "#232630"   # 输入框/气泡底
C_BORDER   = "#2b2f39"   # 描边
C_TEXT     = "#e9ecf1"   # 主文字
C_DIM      = "#8b919d"   # 次要文字
C_ACCENT   = "#f6a821"   # 琥珀橙主色（狗爪暖色）
C_ACCENT_D = "#d98f12"   # 主色 hover
C_SELF_BG  = "#43351a"   # 自己的气泡底（琥珀深色）
C_SELF_TX  = "#ffedb8"   # 自己的气泡文字
C_RED      = "#ef4444"   # 警告红
C_RED_D    = "#b91c1c"
C_RED_BG   = "#331414"   # 警告底色
FONT = "Microsoft YaHei UI"
# 其他用户昵称配色（按 client_id 哈希分配，便于区分发言人）
NAME_COLORS = ["#7aa2f7", "#9ece6a", "#bb9af7", "#f7768e",
               "#7dcfff", "#ff9e64", "#73daca", "#e0af68"]

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChatDog.App.1.0")


def resource_path(relative_path):
    """获取资源绝对路径，兼容开发环境和PyInstaller打包后的环境"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def auto_allow_firewall():
    """自动添加防火墙规则，避免用户手动放行（需管理员权限运行，
    打包时使用 --uac-admin 可自动获得管理员权限）"""
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            rule_name = "ChatDog_UDP_Auto"
            flags = 0x08000000  # 隐藏弹出的黑色CMD窗口
            # 先删除旧规则，避免每次启动重复添加导致规则堆积
            subprocess.run(
                f'netsh advfirewall firewall delete rule name="{rule_name}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags
            )
            subprocess.run(
                f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=UDP localport={PORT}',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags
            )
    except Exception:
        pass


# ---------- 通用模态对话框 ----------
class _Dialog(ctk.CTkToplevel):
    """现代化模态对话框：确认框 / 输入框"""

    def __init__(self, master, title, message, ok_text="确定",
                 cancel_text="取消", entry=False, initial="", danger=False):
        super().__init__(master)
        self.result = None
        self._is_entry = entry
        self.title(title)
        self.configure(fg_color=C_BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        w, h = (430, 268) if entry else (430, 224)
        self.update_idletasks()
        try:
            mx = master.winfo_rootx() + (master.winfo_width() - w) // 2
            my = master.winfo_rooty() + (master.winfo_height() - h) // 2
        except Exception:
            mx, my = 220, 220
        self.geometry(f"{w}x{h}+{mx}+{my}")

        card = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=16,
                            border_width=1, border_color=C_BORDER)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(card, text=title, font=(FONT, 15, "bold"),
                     text_color=C_TEXT, justify="left").pack(anchor="w", padx=18, pady=(14, 4))
        ctk.CTkLabel(card, text=message, font=(FONT, 12),
                     text_color=C_DIM, justify="left", wraplength=374).pack(anchor="w", padx=18)

        if entry:
            self.var = ctk.StringVar(value=initial)
            self.e = ctk.CTkEntry(card, textvariable=self.var, height=42, corner_radius=10,
                                  fg_color=C_SURFACE2, border_width=1, border_color=C_BORDER,
                                  text_color=C_TEXT, font=(FONT, 13))
            self.e.pack(fill="x", padx=18, pady=(12, 0))
            self.e.bind("<Return>", lambda ev: self._ok())

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(14, 16))

        ctk.CTkButton(btns, text=cancel_text, width=100, height=38, corner_radius=10,
                      fg_color=C_SURFACE2, hover_color=C_BORDER, text_color=C_TEXT,
                      font=(FONT, 12), command=self._cancel).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btns, text=ok_text, width=100, height=38, corner_radius=10,
                      fg_color=C_RED if danger else C_ACCENT,
                      hover_color=C_RED_D if danger else C_ACCENT_D,
                      text_color="#ffffff" if danger else "#1c1408",
                      font=(FONT, 12, "bold"), command=self._ok).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda ev: self._cancel())
        self.after(200, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            if self._is_entry:
                self.e.focus_set()
        except Exception:
            pass

    def _ok(self):
        self.result = self.var.get() if self._is_entry else True
        self.destroy()

    def _cancel(self):
        self.result = None if self._is_entry else False
        self.destroy()


def ask_confirm(master, title, message, ok_text="确定", danger=False):
    dlg = _Dialog(master, title, message, ok_text=ok_text, danger=danger)
    master.wait_window(dlg)
    return bool(dlg.result)


def ask_input(master, title, message, initial="", ok_text="确定"):
    dlg = _Dialog(master, title, message, ok_text=ok_text, entry=True, initial=initial)
    master.wait_window(dlg)
    return dlg.result


class ChatDogApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("ChatDog")
        self.geometry("760x740")
        self.minsize(620, 640)
        self.configure(fg_color=C_BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 程序启动时自动放行防火墙
        auto_allow_firewall()

        # 设置窗口和任务栏图标
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # 唯一客户端ID + 昵称
        self.client_id = str(uuid.uuid4())[:8]
        default_name = f"用户_{self.client_id}"
        self.nickname = (ask_input(self, "欢迎来到 ChatDog",
                                   "首次使用，请输入你的昵称：", initial=default_name)
                         or default_name)

        # 创建 UDP socket，开启广播
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', PORT))

        # 在线用户表: client_id -> {"addr": (ip, port), "name": 昵称, "last_seen": 时间戳}
        self.peers = {}
        self.peers_lock = threading.Lock()
        self._bcast_cache = None
        self._bcast_cache_time = 0

        # 默认快捷消息 (1为警告专用，2-0用户可自定义)
        self.shortcut_messages = {
            1: "__ALERT__",
            2: "收到",
            3: "好的",
            4: "稍等",
            5: "在吗？",
            6: "马上到",
            7: "再见",
            8: "谢谢",
            9: "没问题",
            0: "哈哈哈哈"
        }

        # 记录已经收到过的消息ID，防止多网卡导致重复接收
        self.received_msg_ids = set()
        self._first_block = True

        self.setup_ui()
        self.bind_shortcuts()

        # 启动接收线程和心跳广播线程
        self.running = True
        threading.Thread(target=self.receive_loop, daemon=True).start()
        threading.Thread(target=self.announce_loop, daemon=True).start()

        # 本地欢迎提示 + 广播上线通知
        self.append_system("已就绪 · 等待同一局域网内的其他用户上线")
        self.send_message("已上线", msg_type="system")

    # ---------- UI ----------
    def setup_ui(self):
        # ===== 顶栏卡片 =====
        head = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=14,
                            border_width=1, border_color=C_BORDER)
        head.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(head, text="🐶", font=(FONT, 30)).pack(side="left", padx=(16, 10))
        tbox = ctk.CTkFrame(head, fg_color="transparent")
        tbox.pack(side="left", fill="y", pady=12)
        ctk.CTkLabel(tbox, text="ChatDog", font=(FONT, 20, "bold"),
                     text_color=C_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(tbox, text=f"{self.nickname} · 局域网群聊",
                     font=(FONT, 11), text_color=C_DIM, anchor="w").pack(anchor="w")

        # 在线人数徽章（定时刷新）
        self.online_lbl = ctk.CTkLabel(
            head, text=" ● 在线 1 人 ", font=(FONT, 11, "bold"),
            text_color=C_ACCENT, fg_color="#2c2513", corner_radius=8, height=28)
        self.online_lbl.pack(side="right", padx=(8, 12))
        ctk.CTkLabel(head, text=f" UDP {PORT} ", font=(FONT, 11),
                     text_color=C_DIM, fg_color=C_SURFACE2, corner_radius=8, height=28
                     ).pack(side="right")
        self.after(1500, self.refresh_online)

        # ===== 消息区 =====
        self.msg_text = ctk.CTkTextbox(
            self, fg_color=C_BG, corner_radius=0, wrap="word",
            font=(FONT, 12), text_color=C_TEXT, border_width=0, border_spacing=2)
        self.msg_text.pack(fill="both", expand=True, padx=18, pady=(4, 6))
        self.msg_text.configure(state="disabled")
        self.setup_tags()

        # ===== 快捷消息提示 =====
        self.shortcut_lbl = ctk.CTkLabel(self, text="", font=(FONT, 10),
                                         text_color=C_DIM, anchor="w", justify="left",
                                         wraplength=680)
        self.shortcut_lbl.pack(fill="x", padx=24, pady=(0, 4))
        self.update_shortcut_display()

        # ===== 输入区 =====
        inp = ctk.CTkFrame(self, fg_color="transparent")
        inp.pack(fill="x", padx=16, pady=(2, 8))
        self.entry = ctk.CTkEntry(
            inp, placeholder_text="输入消息，Enter 发送…", height=44, corner_radius=12,
            fg_color=C_SURFACE, border_width=1, border_color=C_BORDER,
            text_color=C_TEXT, font=(FONT, 13))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind('<Return>', lambda e: self.send_normal())
        self.entry.focus()
        ctk.CTkButton(inp, text="发送", width=90, height=44, corner_radius=12,
                      fg_color=C_ACCENT, hover_color=C_ACCENT_D, text_color="#1c1408",
                      font=(FONT, 13, "bold"), command=self.send_normal
                      ).pack(side="left", padx=(10, 0))

        # ===== 底部按钮区 =====
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(bot, text="⚙ 快捷消息设置", width=150, height=38, corner_radius=10,
                      fg_color=C_SURFACE, hover_color=C_SURFACE2, border_width=1,
                      border_color=C_BORDER, text_color=C_TEXT, font=(FONT, 12),
                      command=self.open_shortcut_settings).pack(side="left")
        ctk.CTkButton(bot, text="🚨 紧急警告 (Ctrl+1)", width=175, height=38, corner_radius=10,
                      fg_color=C_RED_BG, hover_color="#451a1a", border_width=1,
                      border_color="#5c2323", text_color=C_RED, font=(FONT, 12, "bold"),
                      command=self.send_alert).pack(side="right")

    def _font(self, size, style="normal"):
        """按系统 DPI 缩放生成字体元组（Text tag 不随 CTk 自动缩放）"""
        try:
            scale = self._get_widget_scaling()
        except Exception:
            scale = 1.0
        return (FONT, max(9, int(round(size * scale))), style)

    def setup_tags(self):
        """消息气泡样式（基于 Text tag）。
        注意：必须用内部 _textbox.tag_config，CTk 封装层禁止 font 参数"""
        t = self.msg_text._textbox.tag_config
        t("sys", font=self._font(10, "italic"), foreground=C_DIM,
          justify="center", spacing1=8, spacing3=8)
        t("o_time", font=self._font(9), foreground=C_DIM)
        t("o_bub", font=self._font(12), background=C_SURFACE2, foreground=C_TEXT,
          lmargin1=18, lmargin2=18, rmargin=40, spacing1=5, spacing3=5)
        t("s_time", font=self._font(9), foreground=C_DIM, justify="right", rmargin=16)
        t("s_bub", font=self._font(12), background=C_SELF_BG, foreground=C_SELF_TX,
          justify="right", lmargin1=170, lmargin2=170, rmargin=16, spacing1=5, spacing3=5)
        t("alert", font=self._font(12, "bold"), background=C_RED_BG, foreground="#ff9d9d",
          justify="center", spacing1=8, spacing3=8, lmargin1=18, lmargin2=18, rmargin=18)

    def _name_tag(self, cid):
        """为某用户创建/获取带专属颜色的昵称 tag"""
        tag = f"n_{cid}"
        color = NAME_COLORS[sum(ord(c) for c in str(cid)) % len(NAME_COLORS)]
        try:
            self.msg_text._textbox.tag_config(
                tag, font=self._font(12, "bold"), foreground=color)
        except Exception:
            pass
        return tag

    def _insert(self, text, tags=None):
        self.msg_text.configure(state="normal")
        self.msg_text.insert("end", text, tags)
        self.msg_text.see("end")
        self.msg_text.configure(state="disabled")

    def _sep(self):
        if not self._first_block:
            self.msg_text.configure(state="normal")
            self.msg_text.insert("end", "\n")
            self.msg_text.configure(state="disabled")
        else:
            self._first_block = False

    def append_self(self, content):
        """自己的消息：右对齐琥珀气泡"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._sep()
        self._insert(f"{ts}  我", ("s_time",))
        self._insert("\n")
        self._insert(f"  {content}  ", ("s_bub",))
        self._insert("\n")

    def append_other(self, name, content, cid, ts):
        """别人的消息：左对齐普通气泡，昵称带专属颜色"""
        self._sep()
        self._insert(f" {name} ", (self._name_tag(cid),))
        self._insert(f" {ts}", ("o_time",))
        self._insert("\n")
        self._insert(f"  {content}  ", ("o_bub",))
        self._insert("\n")

    def append_system(self, text):
        self._sep()
        self._insert(f"{text}\n", ("sys",))

    def append_alert(self, text):
        self._sep()
        self._insert(f"{text}", ("alert",))
        self._insert("\n")

    def refresh_online(self):
        try:
            n = len(self.get_active_peers()) + 1
            self.online_lbl.configure(text=f" ● 在线 {n} 人 ")
        except Exception:
            pass
        if self.running:
            self.after(1500, self.refresh_online)

    def update_shortcut_display(self):
        keys = [2, 3, 4, 5, 6, 7, 8, 9, 0]
        parts = [f"Ctrl+{k} {self.shortcut_messages.get(k, '')}"
                 for k in keys if self.shortcut_messages.get(k)]
        self.shortcut_lbl.configure(
            text="快捷消息 · " + "   ".join(parts) if parts else "可在下方设置快捷消息")

    def bind_shortcuts(self):
        # 绑定 Ctrl+0 到 Ctrl+9 (只需绑定到 root，全局生效，避免触发两次)
        for i in range(10):
            self.bind(f'<Control-Key-{i}>', lambda e, key=i: self.handle_shortcut(key))

    # ---------- 快捷键处理 ----------
    def handle_shortcut(self, key):
        if key == 1:
            self.send_alert()
        else:
            msg = self.shortcut_messages.get(key, "")
            if msg:
                self.send_message(msg, "normal")
                self.append_self(msg)

    def open_shortcut_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("快捷消息设置")
        win.configure(fg_color=C_BG)
        win.geometry("420x620")
        win.resizable(False, False)
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="自定义快捷消息", font=(FONT, 16, "bold"),
                     text_color=C_TEXT).pack(pady=(20, 2))
        ctk.CTkLabel(win, text="按 Ctrl + 数字 即可快速发送对应消息",
                     font=(FONT, 11), text_color=C_DIM).pack(pady=(0, 12))

        entries = {}
        for k in [2, 3, 4, 5, 6, 7, 8, 9, 0]:
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=5)
            ctk.CTkLabel(row, text=f"Ctrl + {k}", width=80, font=(FONT, 12, "bold"),
                         text_color=C_ACCENT, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row, height=36, corner_radius=10, fg_color=C_SURFACE2,
                             border_width=1, border_color=C_BORDER, text_color=C_TEXT,
                             font=(FONT, 12))
            e.insert(0, self.shortcut_messages.get(k, ""))
            e.pack(side="left", fill="x", expand=True, padx=(8, 0))
            entries[k] = e

        def save_settings():
            for k, e in entries.items():
                val = e.get().strip()
                if val:
                    self.shortcut_messages[k] = val
            self.update_shortcut_display()
            win.destroy()

        def _grab():
            try:
                win.grab_set()
            except Exception:
                pass
        win.after(200, _grab)
        # 支持键盘操作：Enter 保存，Esc 关闭
        win.bind("<Return>", lambda ev: save_settings())
        win.bind("<Escape>", lambda ev: win.destroy())

        ctk.CTkButton(win, text="保存", height=44, corner_radius=12,
                      fg_color=C_ACCENT, hover_color=C_ACCENT_D, text_color="#1c1408",
                      font=(FONT, 13, "bold"), command=save_settings
                      ).pack(fill="x", padx=22, pady=(14, 20))

    # ---------- 网络辅助 ----------
    def get_broadcast_addrs(self):
        """获取本机所有网卡的广播地址（带缓存）"""
        now = time.time()
        if self._bcast_cache is not None and now - self._bcast_cache_time < 30:
            return self._bcast_cache
        addrs = {BROADCAST_ADDR}
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip.startswith('127.'):
                    continue
                parts = ip.split('.')
                addrs.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
                addrs.add(f"{parts[0]}.{parts[1]}.255.255")
        except Exception:
            pass
        self._bcast_cache = list(addrs)
        self._bcast_cache_time = now
        return self._bcast_cache

    def register_peer(self, client_id, addr, name):
        """收到某个用户的任何数据包后，记录/刷新其地址，供单播使用"""
        if not client_id:
            return
        with self.peers_lock:
            self.peers[client_id] = {
                "addr": addr,
                "name": name,
                "last_seen": time.time(),
            }

    def get_active_peers(self):
        """返回当前在线（未超时）的其他用户地址列表"""
        now = time.time()
        result = []
        with self.peers_lock:
            for cid, info in self.peers.items():
                if now - info["last_seen"] < PEER_TIMEOUT:
                    result.append(info["addr"])
        return result

    def announce_loop(self):
        """周期性发送心跳广播，让其他用户能发现并记住本机地址"""
        while self.running:
            try:
                msg = {
                    "id": self.client_id,
                    "msg_uid": str(uuid.uuid4()),
                    "name": self.nickname,
                    "type": "ping",
                    "content": "",
                    "time": datetime.now().strftime("%H:%M:%S"),
                }
                data = json.dumps(msg).encode('utf-8')
                for bcast in self.get_broadcast_addrs():
                    try:
                        self.sock.sendto(data, (bcast, PORT))
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(ANNOUNCE_INTERVAL)

    def send_message(self, content, msg_type="normal"):
        msg = {
            "id": self.client_id,
            "msg_uid": str(uuid.uuid4()),  # 每条消息的唯一ID，用于去重
            "name": self.nickname,
            "type": msg_type,
            "content": content,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        data = json.dumps(msg).encode('utf-8')
        # 1) 广播：覆盖尚未被发现的在线用户
        for bcast in self.get_broadcast_addrs():
            try:
                self.sock.sendto(data, (bcast, PORT))
            except Exception:
                pass
        # 2) 单播：直接发给每个已知在线用户（修复广播被丢弃导致收不到消息的问题）
        for addr in self.get_active_peers():
            try:
                self.sock.sendto(data, addr)
            except Exception:
                pass

    def send_normal(self):
        content = self.entry.get().strip()
        if not content:
            return
        self.entry.delete(0, "end")
        self.send_message(content, "normal")
        self.append_self(content)

    def send_alert(self):
        if not ask_confirm(
                self, "发送紧急警告",
                "确定要发送【紧急警告】吗？\n\n"
                "所有在线用户的客户端将弹出警告窗口，\n"
                "窗口将会闪烁红光。\n\n"
                "请仅在真正紧急时使用！",
                ok_text="发送警告", danger=True):
            return
        content = ask_input(self, "警告内容", "请输入警告内容：",
                            initial="紧急情况！请立即注意！")
        if not content:
            return
        self.send_message(content, "alert")
        self.append_alert(f"⚠ 你发出了紧急警告: {content}")

    def receive_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                msg = json.loads(data.decode('utf-8'))
                if msg.get('id') == self.client_id:
                    continue
                # 只要收到对方的任何包（包括心跳），就记住对方地址，
                # 之后发消息会同时单播给对方，确保双向可达
                self.register_peer(msg.get('id'), addr, msg.get('name', '未知'))
                self.after(0, lambda m=msg: self.handle_message(m))
            except OSError:
                break
            except Exception:
                pass

    def handle_message(self, msg):
        # 心跳包仅用于在线发现，不显示
        if msg.get('type') == 'ping':
            return

        # 去重逻辑，防止广播+单播/多网卡导致接收两次
        msg_uid = msg.get('msg_uid')
        if not msg_uid or msg_uid in self.received_msg_ids:
            return

        self.received_msg_ids.add(msg_uid)
        # 防止内存无限增长，只保留最近的 100 条记录
        if len(self.received_msg_ids) > 100:
            self.received_msg_ids = set(list(self.received_msg_ids)[-50:])

        t = msg.get('type', 'normal')
        time_str = msg.get('time', '')
        name = msg.get('name', '未知')
        cid = msg.get('id', '')
        content = msg.get('content', '')

        if t == 'alert':
            self.append_alert(f"⚠ 紧急警告来自 {name}: {content}")
            self.show_alert(msg)
        elif t == 'system':
            self.append_system(f"* {name} {content} *")
        else:
            self.append_other(name, content, cid, time_str)
            self.show_notification(msg)

    # ---------- 普通通知（右下角 Toast） ----------
    def show_notification(self, msg):
        notif = ctk.CTkToplevel(self)
        notif.overrideredirect(True)
        notif.attributes('-topmost', True)
        notif.configure(fg_color=C_SURFACE)

        card = ctk.CTkFrame(notif, fg_color=C_SURFACE, corner_radius=12,
                            border_width=1, border_color=C_BORDER)
        card.pack(fill="both", expand=True)

        ctk.CTkLabel(card, text=f"💬 来自: {msg['name']}", font=(FONT, 11, "bold"),
                     text_color=C_ACCENT, anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(card, text=msg['content'], font=(FONT, 12), text_color=C_TEXT,
                     anchor="w", justify="left", wraplength=272).pack(fill="x", padx=14)
        ctk.CTkLabel(card, text=msg['time'], font=(FONT, 9), text_color=C_DIM,
                     anchor="e").pack(fill="x", padx=14, pady=(0, 8))

        w, h = 320, 96
        sw, sh = notif.winfo_screenwidth(), notif.winfo_screenheight()
        notif.geometry(f"{w}x{h}+{sw - w - 24}+{sh - h - 72}")

        notif.bind('<Button-1>', lambda e: notif.destroy())

        notif.attributes('-alpha', 0)
        for i in range(1, 11):
            notif.after(i * 25, lambda a=i / 10: notif.attributes('-alpha', a))
        notif.after(5000, lambda: self.fade_out(notif))

    def fade_out(self, win):
        def step(i=10):
            if not win.winfo_exists():
                return
            if i <= 0:
                win.destroy()
                return
            win.attributes('-alpha', i / 10)
            win.after(25, lambda: step(i - 1))
        step()

    # ---------- 紧急警告弹窗 ----------
    def show_alert(self, msg):
        win = ctk.CTkToplevel(self)
        win.title("ChatDog · 紧急警告")
        win.configure(fg_color="#0d0e11")
        win.attributes('-topmost', True)
        w, h = 520, 360
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        border = ctk.CTkFrame(win, fg_color="transparent", corner_radius=14,
                               border_width=3, border_color=C_RED)
        border.pack(fill="both", expand=True, padx=10, pady=10)

        inner = ctk.CTkFrame(border, fg_color="#0d0e11", corner_radius=12)
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(inner, text="⚠  紧  急  警  告  ⚠",
                     font=(FONT, 26, "bold"), text_color=C_RED).pack(pady=(28, 14))
        ctk.CTkLabel(inner, text=f"来自: {msg['name']}",
                     font=(FONT, 14), text_color=C_TEXT).pack(pady=4)
        ctk.CTkLabel(inner, text=msg['content'],
                     font=(FONT, 18, "bold"), text_color="#ffd166",
                     wraplength=400, justify="center").pack(pady=14, padx=20)
        ctk.CTkLabel(inner, text=f"时间: {msg['time']}",
                     font=(FONT, 10), text_color=C_DIM).pack(pady=4)

        ctk.CTkButton(inner, text="我已知晓，关闭警告", height=46, corner_radius=12,
                      fg_color=C_RED, hover_color=C_RED_D, text_color="#ffffff",
                      font=(FONT, 13, "bold"), command=win.destroy).pack(pady=(18, 22))

        # 弹窗红色闪烁逻辑
        def flash(state=[0]):
            if not win.winfo_exists():
                return
            border.configure(border_color=C_RED if state[0] % 2 == 0 else "#4a0f0f")
            state[0] += 1
            win.after(400, flash)

        flash()

    # ---------- 关闭 ----------
    def on_close(self):
        self.send_message("已下线", "system")
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = ChatDogApp()
    app.mainloop()
