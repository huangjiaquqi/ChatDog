# -*- coding: utf-8 -*-
"""ChatDog - 局域网/直连聊天工具（深色 UI · 三模式版）

启动模式:
  lan     默认模式，同一 WiFi/热点下 UDP 广播+单播自动发现
  server  服务器模式，TCP 监听端口，其他人直连你的 IP:端口
  client  客户端模式，TCP 直连对方的 IP:端口
支持完全无网环境（网线直连等），上次昵称记忆在程序目录 chatdog_profiles.json
"""
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
import random

# ============== 配置 ==============
PORT = 50007                        # 默认模式 UDP 端口（所有客户端必须一致）
BROADCAST_ADDR = '255.255.255.255'  # 受限广播地址（兜底）
PEER_TIMEOUT = 15                   # 在线用户超时时间（秒）
ANNOUNCE_INTERVAL = 3               # 上线广播/心跳间隔（秒）
DEFAULT_TCP_PORT = 50008            # 服务器/客户端模式默认 TCP 端口
# =================================

# ---------- 设计令牌（浅色风格） ----------
C_BG       = "#f4f5f7"   # 全局背景（浅灰白）
C_SURFACE  = "#ffffff"   # 卡片/控件底（纯白）
C_SURFACE2 = "#eceef2"   # 输入框/气泡底（浅灰）
C_BORDER   = "#d9dde5"   # 描边
C_TEXT     = "#22262e"   # 主文字（近黑）
C_DIM      = "#737b87"   # 次要文字（中灰）
C_ACCENT   = "#f5a623"   # 琥珀橙主色（狗爪暖色）
C_ACCENT_D = "#d98f12"   # 主色 hover
C_RED      = "#e5484d"   # 警告红
C_RED_D    = "#b91c1c"
C_RED_BG   = "#fdecec"   # 警告底色（浅红）
FONT = "Microsoft YaHei UI"
# 用户主题色板：每人分配一个主题，名字与气泡同色系
# （名字用深色版保证可读，气泡用同色系亮色版配黑色文字）
USER_THEMES = [
    ("#3b6fd4", "#d6e8ff"),  # 蓝   深蓝名字 / 天空蓝气泡
    ("#4e9a51", "#d9f2d0"),  # 绿   深绿名字 / 嫩草绿气泡
    ("#8a5cd6", "#e8dcff"),  # 紫   深紫名字 / 薰衣草气泡
    ("#d64562", "#ffd9d9"),  # 红   深红名字 / 樱花粉气泡
    ("#0e8fa3", "#d4f3f0"),  # 青   深青名字 / 薄荷青气泡
    ("#d97a2b", "#ffe8d1"),  # 橙   深橙名字 / 蜜桃橙气泡
    ("#b3862d", "#fdf3c8"),  # 黄   深黄名字 / 奶油黄气泡
    ("#2e8e6f", "#d9f2e3"),  # 翠绿 深翠名字 / 浅翠绿气泡
]

# ---------- 叠层通知参数 ----------
TOAST_MR   = 24          # 通知距工作区右侧
TOAST_MB   = 16          # 通知距工作区底部（工作区已排除任务栏）
TOAST_GAP  = 10          # 通知间距
TOAST_LIFE = 4500        # 通知停留时长（毫秒）
TOAST_MAX  = 5           # 最大叠层数


def get_workarea():
    """Windows 工作区物理像素（右/下边界，已排除任务栏）。
    与 Tk 同处一个 DPI 坐标系，定位自洽，不受缩放倍率影响。"""
    class _RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]
    rc = _RECT()
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rc), 0)
        return rc.r, rc.b
    except Exception:
        return None, None


def apply_win11_round_corners(win):
    """Win11+ 让系统给窗口绘制原生圆角（无色键、无暗角）；
    Win10 自动降级为直角，同样干净和谐。"""
    try:
        DWMWA_CORNER = 33      # DWMWA_WINDOW_CORNER_PREFERENCE
        DWMWCP_ROUND = 2
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        if not hwnd:
            hwnd = win.winfo_id()
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd), DWMWA_CORNER,
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), 4) != 0:
            # 失败则尝试直接对自身 hwnd 设置
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(win.winfo_id()), DWMWA_CORNER,
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), 4)
    except Exception:
        pass

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChatDog.App.1.1")


def resource_path(relative_path):
    """获取资源绝对路径，兼容开发环境和PyInstaller打包后的环境"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def app_dir():
    """程序所在目录（打包后为 exe 所在目录），用于存放用户配置"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


PROFILE_FILE = os.path.join(app_dir(), "chatdog_profiles.json")


def load_profiles():
    """读取上次使用的昵称"""
    try:
        with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {"last_nickname": str(data.get("last_nickname", ""))}
    except Exception:
        pass
    return {"last_nickname": ""}


def save_profiles(data):
    try:
        with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_local_ips():
    """获取本机所有可用 IPv4 地址（无网时也能拿到直连网卡地址）"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))   # 不会真正发包，仅触发路由选择
            ip = s.getsockname()[0]
            if ip and ip not in ips:
                ips.append(ip)
        finally:
            s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return sorted(ips) or ["127.0.0.1"]


# 本机 IP 列表缓存：只在进程启动时取一次，保证列表顺序稳定不跳动
_LOCAL_IPS = None


def local_ips():
    global _LOCAL_IPS
    if _LOCAL_IPS is None:
        _LOCAL_IPS = get_local_ips()
    return _LOCAL_IPS


def auto_allow_firewall(protocol, port):
    """自动添加防火墙规则，避免用户手动放行（需管理员权限运行，
    打包时使用 --uac-admin 可自动获得管理员权限）"""
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            rule_name = f"ChatDog_{protocol}_{port}_Auto"
            flags = 0x08000000  # 隐藏弹出的黑色CMD窗口
            # 先删除旧规则，避免每次启动重复添加导致规则堆积
            subprocess.run(
                f'netsh advfirewall firewall delete rule name="{rule_name}"',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=flags
            )
            subprocess.run(
                f'netsh advfirewall firewall add rule name="{rule_name}" '
                f'dir=in action=allow protocol={protocol} localport={port}',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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


# ---------- 叠层通知 Toast ----------
class _Toast:
    """手机通知风格的单条 Toast（叠层与位置由 ChatDogApp 管理）。

    实现要点（修复四角暗色 + 位置偏移）：
    - 纯色窗口 + Win11 系统 DWM 圆角，不用透明色键，杜绝抗锯齿暗角
    - 尺寸先按 DPI 预估，显示后实测真实值再定位，坐标自洽不依赖缩放 API
    - 位置基于 Windows 工作区 API（已排除任务栏），与 Tk 同坐标系
    """
    W = 340   # 逻辑宽（CTk 渲染时按 DPI 放大）
    H = 96    # 逻辑高

    def __init__(self, master, title, content, time_str, cid="", avatar_color=None):
        self.master = master
        # 用户主题深色（头像底色，与名字/气泡同色系）
        self._avatar_color = avatar_color
        # 预估 DPI 倍率（仅用于初始 geometry 与文本换行宽度）
        try:
            self._scale = ctk.ScalingTracker.get_window_scaling(master)
        except Exception:
            self._scale = 1.0
        self._rscale = self._scale          # 实测后的真实渲染倍率
        self.w = max(int(self.W * self._scale), 120)
        self.h = max(int(self.H * self._scale), 56)
        self.cur_x = self.cur_y = 0
        self.target_x = self.target_y = 0
        self._layout_anim_on = False
        self._alive = True
        self.on_close = None  # 由管理器注入

        self.win = ctk.CTkToplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        # 纯色窗口：与卡片同色，四角干净无暗色（圆角由系统 DWM 绘制）
        self.win.configure(fg_color=C_SURFACE)
        apply_win11_round_corners(self.win)

        card = ctk.CTkFrame(self.win, fg_color=C_SURFACE, corner_radius=0,
                            border_width=1, border_color=C_BORDER)
        card.pack(fill="both", expand=True)

        # 头像颜色默认按标题哈希取主题深色（app 会传入用户主题色覆盖）
        theme = USER_THEMES[sum(ord(c) for c in str(cid or title)) % len(USER_THEMES)]
        color = getattr(self, "_avatar_color", None) or theme[0]
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(11, 0))
        avatar_txt = str(title)[:1].upper() if title else "·"
        ctk.CTkLabel(head, text=avatar_txt, width=30, height=30, corner_radius=15,
                     fg_color=color, text_color="#ffffff",
                     font=(FONT, 13, "bold")).pack(side="left")
        ctk.CTkLabel(head, text=title, font=(FONT, 12, "bold"), text_color=C_TEXT,
                     anchor="w").pack(side="left", padx=(10, 8), fill="x", expand=True)
        ctk.CTkLabel(head, text=time_str, font=(FONT, 9), text_color=C_DIM
                     ).pack(side="right")
        ctk.CTkLabel(card, text=content, font=(FONT, 11), text_color=C_DIM,
                     anchor="w", justify="left",
                     wraplength=int((self.W - 72) * self._scale)
                     ).pack(fill="x", padx=(54, 14), pady=(4, 10))

        # 点击任意位置关闭
        self._bind_close(card)

    def measure(self):
        """显示后实测真实渲染尺寸，并推算实际 DPI 倍率（自洽闭环）"""
        try:
            self.win.update_idletasks()
            self.w = max(self.win.winfo_width(), 120)
            self.h = max(self.win.winfo_height(), 56)
            if self.W > 0:
                self._rscale = max(self.w / self.W, 0.5)
        except Exception:
            pass

    def _bind_close(self, widget):
        widget.bind("<Button-1>", lambda e: self.close_now())
        for child in widget.winfo_children():
            self._bind_close(child)

    # ----- 位置动画 -----
    def set_target(self, x, y):
        self.target_x, self.target_y = x, y
        if not self._layout_anim_on:
            self._layout_anim_on = True
            self._layout_step()

    def _layout_step(self):
        if not self._alive or not self.win.winfo_exists():
            self._layout_anim_on = False
            return
        dx = self.target_x - self.cur_x
        dy = self.target_y - self.cur_y
        if abs(dx) < 1 and abs(dy) < 1:
            self.cur_x, self.cur_y = self.target_x, self.target_y
            self._apply_geo()
            self._layout_anim_on = False
            return
        self.cur_x += dx * 0.28
        self.cur_y += dy * 0.28
        self._apply_geo()
        self.win.after(16, self._layout_step)

    def _geo_size(self, pw, ph):
        """物理像素 → geometry 逻辑值（CTk 会把尺寸按 DPI 放大）"""
        return (max(int(round(pw / self._rscale)), 40),
                max(int(round(ph / self._rscale)), 20))

    def _apply_geo(self):
        try:
            gw, gh = self._geo_size(self.w, self.h)
            self.win.geometry(f"{gw}x{gh}+{int(self.cur_x)}+{int(self.cur_y)}")
        except Exception:
            pass

    def fade_in(self):
        a = [0.0]

        def step():
            if not self._alive or not self.win.winfo_exists():
                return
            a[0] = min(1.0, a[0] + 0.12)
            self.win.attributes('-alpha', a[0])
            if a[0] < 1.0:
                self.win.after(18, step)
        step()

    def close_now(self):
        if not self._alive:
            return
        self._alive = False
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass
        try:
            self.win.destroy()
        except Exception:
            pass

    def play_disappear(self):
        """消失动画：从下到上移动 + 快速变小变淡"""
        ox, oy = self.cur_x, self.cur_y
        ow, oh = self.w, self.h          # 实测物理尺寸
        lift = int(52 * self._rscale)    # 上移距离（按实测倍率缩放，视觉一致）
        steps = 12

        def step(i):
            if not self._alive:
                return
            if not self.win.winfo_exists():
                self._alive = False
                return
            if i > steps:
                self._alive = False
                try:
                    self.win.destroy()
                except Exception:
                    pass
                return
            k = i / steps
            pw = int(ow * (1 - 0.42 * k))          # 物理尺寸快速变小
            ph = int(oh * (1 - 0.42 * k))
            gw, gh = self._geo_size(pw, ph)        # 换算回 geometry 逻辑值
            nx = int(ox + (ow - pw) / 2)           # 居中收缩
            ny = int(oy - lift * k)                # 从下到上移动
            try:
                self.win.geometry(f"{gw}x{gh}+{nx}+{ny}")
                self.win.attributes('-alpha', 1.0 - k)  # 变淡
            except Exception:
                pass
            self.win.after(16, lambda: step(i + 1))
        step(0)


# ---------- 启动模式选择窗口 ----------
class LaunchWindow(ctk.CTk):
    MODE_INFO = {
        "lan": ("默认模式 · 局域网", "连接同一 WiFi / 热点，自动发现其他用户"),
        "server": ("服务器模式 · 我做主机", "完全无网可用！其他人直连你的 IP 和端口（网线直连/无路由器场景）"),
        "client": ("客户端模式 · 连接主机", "完全无网可用！输入对方的 IP 和端口直连对方"),
    }

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("light")
        self.title("ChatDog · 启动")
        self.configure(fg_color=C_BG)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(620, sw - 80), min(560, sh - 140)
        self.update_idletasks()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(8, (sh - h) // 2)}")
        self.minsize(560, 480)
        self.result = None

        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        self._mode = ctk.StringVar(value="lan")
        self._port = ctk.StringVar(value=str(DEFAULT_TCP_PORT))
        self._host = ctk.StringVar(value="")
        self._mode_cards = {}
        self._param_areas = {}
        self._copy_btns = []

        self.setup_ui()

    # ---------- UI ----------
    def setup_ui(self):
        # 整体可滚动，适配低分辨率屏幕
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        # ===== 标题区 =====
        head = ctk.CTkFrame(self.scroll, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(20, 4))
        hb = ctk.CTkFrame(head, fg_color="transparent")
        hb.pack(side="left", fill="y")
        ctk.CTkLabel(hb, text="ChatDog", font=(FONT, 22, "bold"),
                     text_color=C_TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(hb, text="选择启动模式 · 支持完全无网环境",
                     font=(FONT, 11), text_color=C_DIM, anchor="w").pack(anchor="w")

        # ===== 模式选择 =====
        ctk.CTkLabel(self.scroll, text="启动模式", font=(FONT, 13, "bold"),
                     text_color=C_TEXT, anchor="w").pack(fill="x", padx=26, pady=(12, 6))

        self._mode_option("lan")
        self._mode_option("server", self._build_server_params)
        self._mode_option("client", self._build_client_params)

        # ===== 启动按钮 =====
        ctk.CTkButton(self.scroll, text="🚀 启动 ChatDog", height=52, corner_radius=14,
                      fg_color=C_ACCENT, hover_color=C_ACCENT_D, text_color="#1c1408",
                      font=(FONT, 15, "bold"), command=self._launch
                      ).pack(fill="x", padx=24, pady=(16, 20))
        self.bind("<Return>", lambda ev: self._launch())

        self._sync_param_visibility()

    def _mode_option(self, value, param_builder=None):
        title, desc = self.MODE_INFO[value]
        card = ctk.CTkFrame(self.scroll, fg_color=C_SURFACE, corner_radius=12,
                            border_width=1, border_color=C_BORDER)
        card.pack(fill="x", padx=24, pady=5)

        rb = ctk.CTkRadioButton(card, text=title, variable=self._mode, value=value,
                                font=(FONT, 13, "bold"), text_color=C_TEXT,
                                fg_color=C_ACCENT, hover_color=C_ACCENT_D,
                                border_color=C_BORDER,
                                command=self._sync_param_visibility)
        rb.pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(card, text=desc, font=(FONT, 10), text_color=C_DIM,
                     anchor="w", justify="left", wraplength=520
                     ).pack(anchor="w", padx=42, pady=(0, 9))

        area = ctk.CTkFrame(card, fg_color="transparent")
        if param_builder:
            param_builder(area)
        self._mode_cards[value] = card
        self._param_areas[value] = area

        def _select(e=None):
            self._mode.set(value)
            self._sync_param_visibility()
        card.bind("<Button-1>", _select)

    def _build_server_params(self, area):
        row = ctk.CTkFrame(area, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(row, text="监听端口", font=(FONT, 11), text_color=C_DIM
                     ).pack(side="left")
        ctk.CTkEntry(row, width=110, height=34, corner_radius=8, textvariable=self._port,
                     fg_color=C_SURFACE2, border_width=1, border_color=C_BORDER,
                     text_color=C_TEXT, font=(FONT, 12)).pack(side="left", padx=(8, 0))

        ipbox = ctk.CTkFrame(area, fg_color="transparent")
        ipbox.pack(fill="x")
        ctk.CTkLabel(ipbox, text="本机 IP（告诉要连你的人，点击复制）：",
                     font=(FONT, 11), text_color=C_DIM).pack(anchor="w")
        for ip in local_ips():
            btn = ctk.CTkButton(ipbox, text=f"  {ip}  📋  ", width=170, height=30,
                                corner_radius=8, fg_color=C_SURFACE2, hover_color=C_BORDER,
                                text_color=C_TEXT, font=(FONT, 11, "bold"),
                                anchor="w")
            btn.configure(command=lambda i=ip, b=btn: self._copy_ip(i, b))
            btn.pack(anchor="w", pady=3)
            self._copy_btns.append(btn)

    def _build_client_params(self, area):
        row1 = ctk.CTkFrame(area, fg_color="transparent")
        row1.pack(fill="x")
        ctk.CTkLabel(row1, text="服务器 IP", width=76, font=(FONT, 11),
                     text_color=C_DIM, anchor="w").pack(side="left")
        ctk.CTkEntry(row1, height=34, corner_radius=8, textvariable=self._host,
                     placeholder_text="例如 192.168.137.1", fg_color=C_SURFACE2,
                     border_width=1, border_color=C_BORDER, text_color=C_TEXT,
                     font=(FONT, 12)).pack(side="left", fill="x", expand=True, padx=(8, 0))
        row2 = ctk.CTkFrame(area, fg_color="transparent")
        row2.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(row2, text="端口", width=76, font=(FONT, 11),
                     text_color=C_DIM, anchor="w").pack(side="left")
        ctk.CTkEntry(row2, width=110, height=34, corner_radius=8, textvariable=self._port,
                     fg_color=C_SURFACE2, border_width=1, border_color=C_BORDER,
                     text_color=C_TEXT, font=(FONT, 12)).pack(side="left", padx=(8, 0))

    def _sync_param_visibility(self):
        m = self._mode.get()
        for v, area in self._param_areas.items():
            if v == m:
                area.pack(fill="x", padx=42, pady=(0, 12))
            else:
                area.pack_forget()
        for v, card in self._mode_cards.items():
            card.configure(border_color=C_ACCENT if v == m else C_BORDER)

    def _copy_ip(self, ip, btn):
        self.clipboard_clear()
        self.clipboard_append(ip)
        btn.configure(text=f"  {ip}  ✓ 已复制  ")
        self.after(1200, lambda: btn.configure(text=f"  {ip}  📋  "))

    # ---------- 启动 ----------
    def _launch(self):
        if self.result is not None:
            return
        m = self._mode.get()
        cfg = {"mode": m, "host": "", "port": DEFAULT_TCP_PORT}
        try:
            port = int(self._port.get())
        except Exception:
            port = 0
        if port <= 0 or port > 65535:
            self._warn("端口无效", "请输入 1 ~ 65535 之间的端口号")
            return
        cfg["port"] = port
        if m == "client":
            host = self._host.get().strip()
            if not host:
                self._warn("缺少 IP", "请输入要连接的服务器 IP 地址")
                return
            cfg["host"] = host
        self.result = cfg
        self.destroy()

    def _warn(self, title, msg):
        dlg = _Dialog(self, title, msg, ok_text="知道了", cancel_text="关闭")
        self.wait_window(dlg)


# ---------- 主应用 ----------
class ChatDogApp(ctk.CTk):
    def __init__(self, mode="lan", host="", port=DEFAULT_TCP_PORT):
        super().__init__()
        ctk.set_appearance_mode("light")
        self.title("ChatDog")
        self.configure(fg_color=C_BG)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(760, sw - 80), min(740, sh - 140)
        self.geometry(f"{w}x{h}+{max(8, (sw - w) // 2)}+{max(8, (sh - h) // 2)}")
        self.minsize(560, 560)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # 连接模式: lan / server / client
        self.mode = mode
        self.host = host
        self.port = port

        # 唯一客户端ID + 昵称（从上次使用记忆中读取，集成在主窗口顶栏可编辑）
        self.client_id = str(uuid.uuid4())[:8]
        prof = load_profiles()
        self.nickname = (prof.get("last_nickname") or "").strip() or f"用户_{self.client_id}"

        # 用户主题：每人进入时随机分配一个（名字深色版 + 气泡亮色版），
        # 名字颜色与气泡颜色同色系，本会话内保持稳定
        self.user_themes = {self.client_id: random.choice(USER_THEMES)}

        # 在线用户表: client_id -> {"addr": (ip, port), "name": 昵称, "last_seen": 时间戳}
        self.peers = {}
        self.peers_lock = threading.Lock()
        self._bcast_cache = None
        self._bcast_cache_time = 0

        # TCP 连接管理
        self.tcp_sock = None            # 客户端模式: 到服务器的连接
        self.srv_sock = None            # 服务器模式: 监听 socket
        self.tcp_conns = []             # 服务器模式: [{"conn":.., "id":.., "name":..}]
        self.tcp_lock = threading.Lock()
        self.roster_members = []        # 客户端模式: 服务器广播的在线名单

        # 叠层通知
        self._toasts = []

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

        # 记录已经收到过的消息ID，防止多网卡/转发导致重复接收
        self.received_msg_ids = set()
        self._first_block = True

        # 程序启动时自动放行防火墙
        if self.mode == "lan":
            auto_allow_firewall("UDP", PORT)
        elif self.mode == "server":
            auto_allow_firewall("TCP", self.port)

        # 设置窗口和任务栏图标
        try:
            icon_path = resource_path("icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # UDP socket 仅默认模式创建
        if self.mode == "lan":
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('0.0.0.0', PORT))
        else:
            self.sock = None

        self.setup_ui()
        self.bind_shortcuts()

        # 启动网络线程
        self.running = True
        if self.mode == "lan":
            threading.Thread(target=self.receive_loop, daemon=True).start()
            threading.Thread(target=self.announce_loop, daemon=True).start()
            self.append_system("已就绪 · 等待同一局域网内的其他用户上线")
            self.send_message("已上线", msg_type="system")
        elif self.mode == "server":
            self.start_server()
        else:
            self.start_client()

    # ---------- UI ----------
    def mode_desc(self):
        if self.mode == "lan":
            return "局域网群聊"
        if self.mode == "server":
            ips = get_local_ips()
            return f"服务器 · 你的 IP {ips[0]} :{self.port}"
        return f"连接 {self.host}:{self.port}"

    def mode_badge(self):
        if self.mode == "lan":
            return f" UDP {PORT} "
        if self.mode == "server":
            return f" 服务器 :{self.port} "
        return f" 客户端 {self.host}:{self.port} "

    def setup_ui(self):
        # ===== 顶栏卡片 =====
        head = ctk.CTkFrame(self, fg_color=C_SURFACE, corner_radius=14,
                            border_width=1, border_color=C_BORDER)
        head.pack(fill="x", padx=16, pady=(16, 10))

        tbox = ctk.CTkFrame(head, fg_color="transparent")
        tbox.pack(side="left", fill="y", pady=12, padx=(18, 0))
        ctk.CTkLabel(tbox, text="ChatDog", font=(FONT, 20, "bold"),
                     text_color=C_TEXT, anchor="w").pack(anchor="w")
        # 昵称输入（集成在主窗口，Enter/失焦保存并广播改名）
        sub = ctk.CTkFrame(tbox, fg_color="transparent")
        sub.pack(anchor="w")
        self.name_entry = ctk.CTkEntry(sub, width=132, height=28, corner_radius=8,
                                       fg_color=C_SURFACE2, border_width=0,
                                       text_color=C_TEXT, font=(FONT, 11))
        self.name_entry.insert(0, self.nickname)
        self.name_entry.pack(side="left")
        self.name_entry.bind("<Return>", self._commit_nickname)
        self.name_entry.bind("<FocusOut>", self._commit_nickname)
        ctk.CTkLabel(sub, text=f"· {self.mode_desc()}", font=(FONT, 11),
                     text_color=C_DIM).pack(side="left", padx=(8, 0))

        # 在线人数徽章（定时刷新）
        self.online_lbl = ctk.CTkLabel(
            head, text=" ● 在线 1 人 ", font=(FONT, 11, "bold"),
            text_color="#a86e00", fg_color="#fdf0d5", corner_radius=8, height=28)
        self.online_lbl.pack(side="right", padx=(8, 12))
        ctk.CTkLabel(head, text=self.mode_badge(), font=(FONT, 11),
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
                      fg_color=C_RED_BG, hover_color="#f5d6d6", border_width=1,
                      border_color="#e8b4b4", text_color=C_RED, font=(FONT, 12, "bold"),
                      command=self.send_alert).pack(side="right")

    # ---------- 昵称（主窗口内编辑 + 记忆 + 广播改名） ----------
    def _commit_nickname(self, event=None):
        try:
            new = self.name_entry.get().strip()
        except Exception:
            return
        if not new:
            try:
                self.name_entry.delete(0, "end")
                self.name_entry.insert(0, self.nickname)
            except Exception:
                pass
            return
        if new == self.nickname:
            return
        old = self.nickname
        self.nickname = new
        prof = load_profiles()
        prof["last_nickname"] = new
        save_profiles(prof)
        self.append_system(f"你已改名为 {new}")
        try:
            self.send_message(f"{old} 已改名为 {new}", "system")
            if self.mode == "server":
                self.broadcast_roster()
        except Exception:
            pass

    def _font(self, size, style="normal"):
        """按系统 DPI 缩放生成字体元组（Text tag 不随 CTk 自动缩放）"""
        try:
            scale = self._get_widget_scaling()
        except Exception:
            scale = 1.0
        return (FONT, max(9, int(round(size * scale))), style)

    def setup_tags(self):
        """消息样式（基于 Text tag）。
        注意：必须用内部 _textbox.tag_config，CTk 封装层禁止 font 参数。
        气泡 tag 按用户动态创建（_bubble_tag），颜色进入时随机分配。"""
        t = self.msg_text._textbox.tag_config
        t("sys", font=self._font(10, "italic"), foreground=C_DIM,
          justify="center", spacing1=8, spacing3=8)
        t("o_time", font=self._font(9), foreground=C_DIM)
        t("s_time", font=self._font(9), foreground=C_DIM, justify="right", rmargin=16)
        t("alert", font=self._font(12, "bold"), background=C_RED_BG, foreground="#c0272d",
          justify="center", spacing1=8, spacing3=8, lmargin1=18, lmargin2=18, rmargin=18)

    def _get_theme(self, cid):
        """获取（必要时随机分配）某用户的主题 (名字深色, 气泡亮色)"""
        if cid not in self.user_themes:
            self.user_themes[cid] = random.choice(USER_THEMES)
        return self.user_themes[cid]

    def _name_tag(self, cid):
        """为某用户创建/获取带专属颜色的昵称 tag（与气泡同主题）"""
        tag = f"n_{cid}"
        color = self._get_theme(cid)[0]
        try:
            self.msg_text._textbox.tag_config(
                tag, font=self._font(12, "bold"), foreground=color)
        except Exception:
            pass
        return tag

    def _insert_bubble(self, content, mine=False, cid=None):
        """插入圆角聊天气泡（嵌入式框架，自己与他人逻辑完全一致）。

        彻底弃用 Text tag 背景方案（背景是否贴合文字受 justify/lmargin/
        rmargin 组合影响，会出现铺满整行的不可控行为），改为：
        - 气泡 = 嵌入 Text 的圆角 CTkFrame，宽度随内容收缩，物理上
          保证"气泡长度 = 消息长度"，长消息自动换行；
        - 颜色 = 用户进入时随机分配的亮色，文字统一黑色；
        - 行对齐用无背景的 justify tag：自己靠右、他人靠左。
        """
        tb = self.msg_text._textbox
        key = self.client_id if mine else (cid or "anon")
        bubble_color = self._get_theme(key)[1]

        # 长消息换行宽度（预留两侧边距与气泡内边距）
        try:
            maxw = max(220, tb.winfo_width() - 160)
        except Exception:
            maxw = 400

        frm = ctk.CTkFrame(tb, fg_color=bubble_color, corner_radius=14)
        ctk.CTkLabel(frm, text=content, font=self._font(12),
                    text_color="#1a1a1a", justify="left",
                    wraplength=maxw).pack(padx=12, pady=7)
        frm.update_idletasks()

        tag = f"ln_{uuid.uuid4().hex[:8]}"
        tb.configure(state="normal")
        # 注意：Tk 的 "end" 插入实际发生在末尾换行符之前，
        # 因此先补一个换行起新行，窗口恰好落在该行，tag 才能正确覆盖
        tb.insert("end", "\n")
        start = tb.index("end-1c")
        tb.window_create(start, window=frm)
        tb.tag_add(tag, start, start + "+1c")
        tb.insert("end", "\n")
        tb.configure(state="disabled")
        # 行对齐：无背景 tag，只控制整行左右对齐（规避背景铺满问题）
        tb.tag_config(tag, justify="right" if mine else "left",
                      lmargin1=18, lmargin2=18, rmargin=18)
        tb.see("end")

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
        """自己的消息：右对齐随机亮色圆角气泡"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._sep()
        self._insert(f"{ts}  我", ("s_time",))
        self._insert("\n")
        self._insert_bubble(content, mine=True)

    def append_other(self, name, content, cid, ts):
        """别人的消息：左对齐随机亮色圆角气泡，昵称带专属颜色"""
        self._sep()
        self._insert(f" {name} ", (self._name_tag(cid),))
        self._insert(f" {ts}", ("o_time",))
        self._insert("\n")
        self._insert_bubble(content, mine=False, cid=cid)

    def append_system(self, text):
        self._sep()
        self._insert(f"{text}\n", ("sys",))

    def append_alert(self, text):
        self._sep()
        self._insert(f"{text}", ("alert",))
        self._insert("\n")

    def refresh_online(self):
        try:
            self.online_lbl.configure(text=f" ● 在线 {self.get_online_count()} 人 ")
        except Exception:
            pass
        if self.running:
            self.after(1500, self.refresh_online)

    def get_online_count(self):
        if self.mode == "lan":
            return len(self.get_active_peers()) + 1
        if self.mode == "server":
            with self.tcp_lock:
                return len(self.tcp_conns) + 1
        return max(1, len(self.roster_members))

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

    # ================= 网络层：默认模式(UDP) =================
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

    # ================= 网络层：服务器模式(TCP) =================
    def start_server(self):
        try:
            self.srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.srv_sock.bind(('0.0.0.0', self.port))
            self.srv_sock.listen(20)
            self.srv_sock.settimeout(1.0)
        except Exception as e:
            self.append_system(f"× 服务器启动失败: {e}")
            return
        threading.Thread(target=self.server_accept_loop, daemon=True).start()
        self.append_system(f"服务器模式 · 正在监听端口 {self.port}，等待其他人连接")
        ips = ", ".join(local_ips())
        self.append_system(f"把你的 IP 和端口告诉其他人即可互连 → {ips} :{self.port}")

    def server_accept_loop(self):
        while self.running:
            try:
                conn, addr = self.srv_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
            threading.Thread(target=self.server_client_loop, args=(conn, addr),
                             daemon=True).start()

    def server_client_loop(self, conn, addr):
        """服务器处理单个客户端连接：收消息、显示、转发"""
        buf = b""
        name = "未知"
        cid = None
        try:
            while self.running:
                data = conn.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode('utf-8'))
                    except Exception:
                        continue
                    if msg.get('id') == self.client_id:
                        continue
                    t = msg.get('type', 'normal')
                    cid = msg.get('id') or cid
                    name = msg.get('name') or name
                    if t == 'hello':
                        # 客户端上线：注册并广播加入消息 + 在线名单
                        self._srv_register(conn, cid, name)
                        join = {"id": cid, "msg_uid": str(uuid.uuid4()), "name": name,
                                "type": "system", "content": "加入了聊天",
                                "time": datetime.now().strftime("%H:%M:%S")}
                        self._safe_after(lambda n=name: self.append_system(f"* {n} 加入了聊天 *"))
                        self.server_broadcast((json.dumps(join) + "\n").encode('utf-8'))
                        self.broadcast_roster()
                        continue
                    if t == 'ping' or t == 'roster':
                        continue
                    # 本地显示 + 转发给其他客户端
                    self._safe_after(lambda m=msg: self.handle_message(m))
                    self.server_relay(conn, line + b"\n")
        except Exception:
            pass
        finally:
            self._srv_unregister(conn, name)

    def _srv_register(self, conn, cid, name):
        with self.tcp_lock:
            for c in self.tcp_conns:
                if c["conn"] is conn:
                    c["id"] = cid
                    c["name"] = name
                    break
            else:
                self.tcp_conns.append({"conn": conn, "id": cid, "name": name})

    def _srv_unregister(self, conn, name):
        try:
            conn.close()
        except Exception:
            pass
        with self.tcp_lock:
            self.tcp_conns = [c for c in self.tcp_conns if c["conn"] is not conn]
        leave = {"id": str(uuid.uuid4())[:8], "msg_uid": str(uuid.uuid4()), "name": name,
                 "type": "system", "content": "离开了聊天",
                 "time": datetime.now().strftime("%H:%M:%S")}
        self._safe_after(lambda n=name: self.append_system(f"* {n} 离开了聊天 *"))
        self.server_broadcast((json.dumps(leave) + "\n").encode('utf-8'))
        self.broadcast_roster()

    def server_broadcast(self, data):
        """服务器：把数据发给所有已连接的客户端"""
        with self.tcp_lock:
            conns = [c["conn"] for c in self.tcp_conns]
        for c in conns:
            try:
                c.sendall(data)
            except Exception:
                pass

    def server_relay(self, from_conn, data):
        """服务器：把某客户端的消息转发给其他所有客户端"""
        with self.tcp_lock:
            conns = [c["conn"] for c in self.tcp_conns if c["conn"] is not from_conn]
        for c in conns:
            try:
                c.sendall(data)
            except Exception:
                pass

    def broadcast_roster(self):
        """服务器：向所有客户端广播当前在线名单"""
        members = [{"id": self.client_id, "name": self.nickname}]
        with self.tcp_lock:
            for c in self.tcp_conns:
                if c.get("id"):
                    members.append({"id": c["id"], "name": c["name"]})
        msg = {"id": self.client_id, "msg_uid": str(uuid.uuid4()), "name": self.nickname,
               "type": "roster", "members": members, "content": "",
               "time": datetime.now().strftime("%H:%M:%S")}
        self.server_broadcast((json.dumps(msg) + "\n").encode('utf-8'))

    # ================= 网络层：客户端模式(TCP) =================
    def start_client(self):
        self.append_system(f"客户端模式 · 正在连接 {self.host}:{self.port} …")
        threading.Thread(target=self.client_loop, daemon=True).start()

    def client_loop(self):
        """客户端主循环：连接服务器，断开后每 3 秒自动重连"""
        while self.running:
            sock = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=5)
                sock.settimeout(None)
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
                with self.tcp_lock:
                    self.tcp_sock = sock
                self._safe_after(lambda: self.append_system(
                    f"已连接服务器 {self.host}:{self.port}"))
                hello = {"id": self.client_id, "msg_uid": str(uuid.uuid4()),
                         "name": self.nickname, "type": "hello", "content": "",
                         "time": datetime.now().strftime("%H:%M:%S")}
                sock.sendall((json.dumps(hello) + "\n").encode('utf-8'))
                buf = b""
                while self.running:
                    data = sock.recv(65536)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            msg = json.loads(line.decode('utf-8'))
                        except Exception:
                            continue
                        if msg.get('id') == self.client_id:
                            continue
                        self._safe_after(lambda m=msg: self.handle_message(m))
            except Exception:
                pass
            finally:
                with self.tcp_lock:
                    self.tcp_sock = None
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if not self.running:
                break
            self._safe_after(lambda: self.append_system(
                f"与服务器 {self.host}:{self.port} 断开，3 秒后自动重连…"))
            time.sleep(3)

    def _safe_after(self, fn):
        """从网络线程安全地调度 UI 操作"""
        try:
            self.after(0, fn)
        except Exception:
            pass

    # ================= 统一发送入口 =================
    def send_message(self, content, msg_type="normal"):
        msg = {
            "id": self.client_id,
            "msg_uid": str(uuid.uuid4()),  # 每条消息的唯一ID，用于去重
            "name": self.nickname,
            "type": msg_type,
            "content": content,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        if self.mode == "lan":
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
        elif self.mode == "server":
            self.server_broadcast((json.dumps(msg) + "\n").encode('utf-8'))
        elif self.mode == "client":
            with self.tcp_lock:
                s = self.tcp_sock
            if s:
                try:
                    s.sendall((json.dumps(msg) + "\n").encode('utf-8'))
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

    # ================= 消息处理 =================
    def handle_message(self, msg):
        # 心跳/hello/roster 包仅用于在线发现与名单同步，不显示
        t = msg.get('type', 'normal')
        if t in ('ping', 'hello', 'roster'):
            if t == 'roster':
                self.roster_members = msg.get('members', [])
            return

        # 去重逻辑，防止广播+单播/多网卡/服务器转发导致重复接收
        msg_uid = msg.get('msg_uid')
        if not msg_uid or msg_uid in self.received_msg_ids:
            return

        self.received_msg_ids.add(msg_uid)
        # 防止内存无限增长，只保留最近的 100 条记录
        if len(self.received_msg_ids) > 100:
            self.received_msg_ids = set(list(self.received_msg_ids)[-50:])

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

    # ---------- 叠层通知中心（手机通知风格） ----------
    def show_notification(self, msg):
        self.push_toast(msg.get('name', '未知'), msg.get('content', ''),
                        msg.get('time', ''), msg.get('id', ''))

    def push_toast(self, title, content, time_str, cid=""):
        """新增一条通知：在屏幕内目标位淡入出现，其余通知向上推（叠层效果）。

        注意：窗口必须始终在屏幕内——完全屏幕外的 Tk 窗口不会收到
        绘制事件，canvas 缓冲为空，移回后显示空白（CTk 不因纯移动重绘）。
        """
        # 头像底色 = 该用户主题深色（与名字/气泡同色系）
        avatar_color = self._get_theme(cid)[0] if cid else None
        toast = _Toast(self, title, content, time_str, cid,
                       avatar_color=avatar_color)
        toast.on_close = lambda t=toast: self._remove_toast(t)
        self._toasts.insert(0, toast)  # 索引 0 = 最底部 = 最新
        while len(self._toasts) > TOAST_MAX:
            old = self._toasts.pop()
            old.on_close = None
            old.play_disappear()

        wa_r, wa_b = get_workarea()
        if wa_r is None:
            wa_r = self.winfo_screenwidth()
            wa_b = self.winfo_screenheight()
        # 1) 按预估尺寸先算屏幕内初始位置，显示窗口（确保 canvas 被绘制）
        toast.cur_x = wa_r - TOAST_MR - toast.w
        toast.cur_y = wa_b - TOAST_MB - toast.h
        toast.target_x, toast.target_y = toast.cur_x, toast.cur_y
        try:
            toast._apply_geo()          # 屏幕内 geometry（withdraw 状态下设置）
            toast.win.deiconify()
            toast.measure()             # 实测真实渲染尺寸
        except Exception:
            pass
        # 2) 用实测尺寸校正位置（差异仅几个像素，随叠层动画平滑归位）
        toast.cur_x = wa_r - TOAST_MR - toast.w
        toast.cur_y = wa_b - TOAST_MB - toast.h
        toast.target_x, toast.target_y = toast.cur_x, toast.cur_y
        toast.fade_in()
        self._relayout_toasts()          # 旧通知向上推，新通知归位
        toast.win.after(TOAST_LIFE, lambda t=toast: self._expire_toast(t))

    def _relayout_toasts(self):
        """从下往上重新排布所有通知（底部最新，向上堆叠）"""
        if not self._toasts:
            return
        wa_r, wa_b = get_workarea()
        if wa_r is None:
            try:
                wa_r = self.winfo_screenwidth()
                wa_b = self.winfo_screenheight()
            except Exception:
                return
        base = wa_b - TOAST_MB               # 最底通知底边的目标线
        for i, t in enumerate(self._toasts):
            y = base - (i + 1) * t.h - i * TOAST_GAP
            t.set_target(wa_r - TOAST_MR - t.w, y)

    def _expire_toast(self, toast):
        """通知到时自动消失：其余通知下移，本条向上飞出并缩小变淡"""
        if toast not in self._toasts:
            return
        self._toasts.remove(toast)
        self._relayout_toasts()
        toast.play_disappear()

    def _remove_toast(self, toast):
        """手动点击关闭通知"""
        if toast in self._toasts:
            self._toasts.remove(toast)
            self._relayout_toasts()

    # ---------- 紧急警告弹窗 ----------
    def show_alert(self, msg):
        win = ctk.CTkToplevel(self)
        win.title("ChatDog · 紧急警告")
        win.configure(fg_color="#ffffff")
        win.attributes('-topmost', True)
        w, h = 520, 360
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        border = ctk.CTkFrame(win, fg_color="transparent", corner_radius=14,
                               border_width=3, border_color=C_RED)
        border.pack(fill="both", expand=True, padx=10, pady=10)

        inner = ctk.CTkFrame(border, fg_color="#ffffff", corner_radius=12)
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(inner, text="⚠  紧  急  警  告  ⚠",
                     font=(FONT, 26, "bold"), text_color=C_RED).pack(pady=(28, 14))
        ctk.CTkLabel(inner, text=f"来自: {msg['name']}",
                     font=(FONT, 14), text_color=C_TEXT).pack(pady=4)
        ctk.CTkLabel(inner, text=msg['content'],
                     font=(FONT, 18, "bold"), text_color="#b45309",
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
            border.configure(border_color=C_RED if state[0] % 2 == 0 else "#f3c6c6")
            state[0] += 1
            win.after(400, flash)

        flash()

    # ---------- 关闭 ----------
    def on_close(self):
        try:
            if self.mode == "lan":
                self.send_message("已下线", "system")
            elif self.mode == "client":
                with self.tcp_lock:
                    s = self.tcp_sock
                if s:
                    self.send_message("已下线", "system")
            elif self.mode == "server":
                bye = {"id": self.client_id, "msg_uid": str(uuid.uuid4()),
                       "name": "服务器", "type": "system", "content": "已关闭",
                       "time": datetime.now().strftime("%H:%M:%S")}
                self.server_broadcast((json.dumps(bye) + "\n").encode('utf-8'))
        except Exception:
            pass
        self.running = False
        for attr in ("sock", "srv_sock"):
            s = getattr(self, attr, None)
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        with self.tcp_lock:
            s = self.tcp_sock
        if s:
            try:
                s.close()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    launch = LaunchWindow()
    launch.mainloop()
    cfg = launch.result
    if cfg:
        app = ChatDogApp(mode=cfg["mode"], host=cfg.get("host", ""),
                         port=cfg.get("port", DEFAULT_TCP_PORT))
        app.mainloop()
