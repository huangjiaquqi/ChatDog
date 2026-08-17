import socket
import threading
import json
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
from datetime import datetime
import uuid
import platform
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

# 强制设置任务栏图标（解决Windows将打包后的exe归类为Python默认图标的问题）
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
        # 检查是否是管理员权限
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
            # 静默执行 netsh 命令放行 UDP 端口
            subprocess.run(
                f'netsh advfirewall firewall add rule name="{rule_name}" dir=in action=allow protocol=UDP localport={PORT}',
                shell=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                creationflags=flags
            )
    except Exception:
        pass


class ChatDog:
    def __init__(self, root):
        self.root = root
        self.root.title("ChatDog")
        self.root.geometry("600x680")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 程序启动时自动放行防火墙
        auto_allow_firewall()

        # 设置窗口和任务栏图标
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # 唯一客户端ID + 昵称
        self.client_id = str(uuid.uuid4())[:8]
        default_name = f"用户_{self.client_id}"
        self.nickname = (simpledialog.askstring("ChatDog", "请输入你的昵称：",
                                                initialvalue=default_name)
                         or default_name)

        # 创建 UDP socket，开启广播
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('0.0.0.0', PORT))

        # 在线用户表: client_id -> {"addr": (ip, port), "name": 昵称, "last_seen": 时间戳}
        # 修复关键：消息除了广播，还会单播发送给每个已知在线用户，
        # 避免部分路由器/热点丢弃广播包导致"离得远的用户收不到消息"
        self.peers = {}
        self.peers_lock = threading.Lock()
        # 广播地址缓存（避免频繁做 DNS 查询枚举本机网卡）
        self._bcast_cache = None
        self._bcast_cache_time = 0

        # 默认快捷消息 (1为警告专用，2-0用户可自定义)
        self.shortcut_messages = {
            1: "__ALERT__",  # 特殊标记
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

        self.setup_ui()
        self.bind_shortcuts()

        # 启动接收线程和心跳广播线程
        self.running = True
        threading.Thread(target=self.receive_loop, daemon=True).start()
        threading.Thread(target=self.announce_loop, daemon=True).start()

        # 广播上线通知
        self.send_message("已上线", msg_type="system")

    # ---------- UI ----------
    def setup_ui(self):
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(top, text=f"用户: {self.nickname}", fg="#333", font=('Microsoft YaHei', 11, 'bold')).pack(side=tk.LEFT)
        tk.Label(top, text=f"端口 {PORT}  ·  广播 {BROADCAST_ADDR}",
                 fg="gray").pack(side=tk.RIGHT)

        # 消息显示区
        self.msg_text = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, state='disabled',
            font=('Microsoft YaHei', 10))
        self.msg_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.msg_text.tag_config('normal', foreground='#222')
        self.msg_text.tag_config('system', foreground='gray',
                                font=('Microsoft YaHei', 9, 'italic'))
        self.msg_text.tag_config('alert',  foreground='red',
                                font=('Microsoft YaHei', 10, 'bold'))
        self.msg_text.tag_config('self',   foreground='#1565c0')

        # 快捷键提示区
        self.shortcut_lbl = tk.Label(self.root, text="", fg="#555", font=('Microsoft YaHei', 9), justify=tk.LEFT)
        self.shortcut_lbl.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.update_shortcut_display()

        # 输入区
        inp = tk.Frame(self.root)
        inp.pack(fill=tk.X, padx=10, pady=5)
        self.entry = tk.Entry(inp, font=('Microsoft YaHei', 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind('<Return>', lambda e: self.send_normal())
        self.entry.focus()
        tk.Button(inp, text="发送", width=8,
                  command=self.send_normal).pack(side=tk.LEFT, padx=5)

        # 底部按钮区
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        tk.Button(btn_frame, text="设置快捷键 (Ctrl+2~0)",
                  command=self.open_shortcut_settings).pack(side=tk.LEFT)
        
        tk.Button(btn_frame, text="发送紧急警告 (Ctrl+1)",
                  command=self.send_alert,
                  bg='#d32f2f', fg='white',
                  activebackground='#b71c1c',
                  font=('Microsoft YaHei', 10, 'bold'),
                  relief=tk.RAISED, bd=2,
                  padx=10, pady=5).pack(side=tk.RIGHT)

    def update_shortcut_display(self):
        text = "快捷消息:  "
        keys = [2, 3, 4, 5, 6, 7, 8, 9, 0]
        for k in keys:
            msg = self.shortcut_messages.get(k, "")
            if msg:
                text += f"[Ctrl+{k}]:{msg}  "
        self.shortcut_lbl.config(text=text.strip())

    def bind_shortcuts(self):
        # 绑定 Ctrl+0 到 Ctrl+9 (只需绑定到 root，全局生效，避免触发两次)
        for i in range(10):
            self.root.bind(f'<Control-Key-{i}>', lambda e, key=i: self.handle_shortcut(key))

    # ---------- 快捷键处理 ----------
    def handle_shortcut(self, key):
        if key == 1:
            self.send_alert()
        else:
            msg = self.shortcut_messages.get(key, "")
            if msg:
                self.send_message(msg, "normal")
                self.append_message(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{self.nickname}(我): {msg}", 'self')

    def open_shortcut_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置快捷消息")
        win.geometry("350x450")
        win.attributes('-topmost', True)
        win.grab_set()  # 模态窗口

        tk.Label(win, text="设置 Ctrl+2 到 Ctrl+0 的快捷消息：", font=('Microsoft YaHei', 10, 'bold')).pack(pady=10)

        entries = {}
        keys = [2, 3, 4, 5, 6, 7, 8, 9, 0]
        
        for k in keys:
            frame = tk.Frame(win)
            frame.pack(fill=tk.X, padx=20, pady=5)
            tk.Label(frame, text=f"Ctrl + {k} :", width=8).pack(side=tk.LEFT)
            entry = tk.Entry(frame, width=25)
            entry.insert(0, self.shortcut_messages.get(k, ""))
            entry.pack(side=tk.LEFT, padx=5)
            entries[k] = entry

        def save_settings():
            for k, entry in entries.items():
                val = entry.get().strip()
                if val:
                    self.shortcut_messages[k] = val
            self.update_shortcut_display()
            win.destroy()

        tk.Button(win, text="保存", command=save_settings, bg='#4caf50', fg='white', font=('Microsoft YaHei', 10, 'bold')).pack(pady=20)

    # ---------- 消息收发 ----------
    def append_message(self, text, tag='normal'):
        self.msg_text.config(state='normal')
        self.msg_text.insert(tk.END, text + '\n', tag)
        self.msg_text.see(tk.END)
        self.msg_text.config(state='disabled')

    # ---------- 网络辅助 ----------
    def get_broadcast_addrs(self):
        """获取本机所有网卡的广播地址（带缓存）。
        除了 255.255.255.255 受限广播，还向每个子网广播，
        提高在各类路由器/热点下的可达性。"""
        now = time.time()
        if self._bcast_cache is not None and now - self._bcast_cache_time < 30:
            return self._bcast_cache
        addrs = {BROADCAST_ADDR}
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip.startswith('127.'):
                    continue
                # 按常见子网掩码推算广播地址，覆盖绝大多数家用/热点场景
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
        """周期性发送心跳广播，让其他用户能发现并记住本机地址。
        即使广播包被丢弃，对方收到单播消息后同样会注册本机地址。"""
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
        self.entry.delete(0, tk.END)
        self.send_message(content, "normal")
        self.append_message(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"{self.nickname}(我): {content}", 'self')

    def send_alert(self):
        if not messagebox.askyesno(
                "ChatDog 确认",
                "确定要发送【紧急警告】吗？\n\n"
                "所有在线用户的客户端将弹出警告窗口，\n"
                "窗口将会闪烁红光。\n\n"
                "请仅在真正紧急时使用！"):
            return
        content = simpledialog.askstring(
            "警告内容", "请输入警告内容：",
            initialvalue="紧急情况！请立即注意！")
        if not content:
            return
        self.send_message(content, "alert")
        self.append_message(
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"⚠ 你发出了紧急警告: {content}", 'alert')

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
                self.root.after(0, lambda m=msg: self.handle_message(m))
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
            return  # 如果已经处理过这条消息，直接忽略

        self.received_msg_ids.add(msg_uid)
        # 防止内存无限增长，只保留最近的 100 条记录
        if len(self.received_msg_ids) > 100:
            self.received_msg_ids = set(list(self.received_msg_ids)[-50:])

        t = msg.get('type', 'normal')
        time_str = msg.get('time', '')
        name = msg.get('name', '未知')
        content = msg.get('content', '')

        if t == 'alert':
            self.append_message(
                f"[{time_str}] ⚠ 紧急警告来自 {name}: {content}", 'alert')
            self.show_alert(msg)
        elif t == 'system':
            self.append_message(f"[{time_str}] * {name} {content} *", 'system')
        else:
            self.append_message(f"[{time_str}] {name}: {content}", 'normal')
            self.show_notification(msg)

    # ---------- 普通通知 ----------
    def show_notification(self, msg):
        notif = tk.Toplevel(self.root)
        notif.overrideredirect(True)
        notif.attributes('-topmost', True)
        # 背景改为白色，并添加红色边框 (highlightthickness控制边框粗细)
        notif.configure(bg='white', highlightbackground='#ff0000', highlightthickness=3)

        frame = tk.Frame(notif, bg='white', padx=15, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # 标题改为红色
        tk.Label(frame, text=f"来自: {msg['name']}",
                 fg='#d32f2f', bg='white',
                 font=('Microsoft YaHei', 9, 'bold')).pack(anchor='w')
        # 内容改为黑色
        tk.Label(frame, text=msg['content'], fg='#222222', bg='white',
                 font=('Microsoft YaHei', 10),
                 wraplength=280, justify='left').pack(anchor='w', pady=(3, 0))
        # 时间保持灰色
        tk.Label(frame, text=msg['time'], fg='gray', bg='white',
                 font=('Microsoft YaHei', 8)).pack(anchor='e')

        w, h = 320, 90
        sw, sh = notif.winfo_screenwidth(), notif.winfo_screenheight()
        notif.geometry(f"{w}x{h}+{sw - w - 20}+{sh - h - 60}")

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
        win = tk.Toplevel(self.root)
        win.title("ChatDog 紧急警告")
        win.geometry("500x350")
        win.attributes('-topmost', True)
        win.configure(bg='black')

        # 居中显示
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - 500) // 2
        y = (sh - 350) // 2
        win.geometry(f"500x350+{x}+{y}")

        # 闪烁的边框
        flash_frame = tk.Frame(win, bg='#ff0000')
        flash_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 内容区
        inner = tk.Frame(flash_frame, bg='black')
        inner.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(inner, text="⚠  紧  急  警  告  ⚠",
                 fg='#ff1744', bg='black',
                 font=('Microsoft YaHei', 28, 'bold')
                 ).pack(pady=(30, 20))

        tk.Label(inner, text=f"来自: {msg['name']}",
                 fg='white', bg='black',
                 font=('Microsoft YaHei', 14)).pack(pady=5)

        tk.Label(inner, text=msg['content'],
                 fg='#ffeb3b', bg='black',
                 font=('Microsoft YaHei', 18, 'bold'),
                 wraplength=400, justify='center').pack(pady=20)

        tk.Label(inner, text=f"时间: {msg['time']}",
                 fg='gray', bg='black',
                 font=('Microsoft YaHei', 10)).pack(pady=5)

        btn = tk.Button(inner, text="我已知晓，关闭警告",
                  command=win.destroy,
                  bg='#d32f2f', fg='white',
                  activebackground='#b71c1c',
                  font=('Microsoft YaHei', 12, 'bold'),
                  padx=20, pady=8)
        btn.pack(pady=20)

        # 弹窗红色闪烁逻辑
        def flash(state=[0]):
            if not win.winfo_exists():
                return
            color = '#ff0000' if state[0] % 2 == 0 else '#5a0000'
            flash_frame.configure(bg=color)
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
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatDog(root)
    root.mainloop()
