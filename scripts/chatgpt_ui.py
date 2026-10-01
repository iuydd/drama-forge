#!/usr/bin/env python3
"""本机 ChatGPT 桌面版大脑通道的 UI 小工具（macOS，Python + Quartz + osascript）。

用法见 references/brain-chatgpt-desktop.md。坐标一律用“半尺寸截图”的像素，
在 Retina 屏上等于屏幕逻辑坐标（点），可直接传给 click。

  python scripts/chatgpt_ui.py activate
  python scripts/chatgpt_ui.py shot  OUT.png
  python scripts/chatgpt_ui.py click X Y [等待秒] [OUT.png]
  python scripts/chatgpt_ui.py file  /绝对路径/附件.md        # 文件放进剪贴板
  python scripts/chatgpt_ui.py text  /绝对路径/消息.txt        # 文本按 UTF-8 放进剪贴板
  python scripts/chatgpt_ui.py paste [等待秒] [OUT.png]        # cmd+V
  python scripts/chatgpt_ui.py clip  OUT.txt                  # 剪贴板文本存盘（取回回复用）
  python scripts/chatgpt_ui.py bottom X Y OUT.png            # 鼠标移到对话区(X,Y)，滚到底再截图（对话区不会自动滚）
  python scripts/chatgpt_ui.py peek  OUT.png                  # 不切前台、不动鼠标，只截 ChatGPT 窗口（用户在用电脑时查看进度）
  python scripts/chatgpt_ui.py front                          # 打印当前前台应用名
"""
import subprocess
import sys
import time

import Quartz

APP_ID = "com.openai.codex"  # 新版 ChatGPT.app 的 bundle id 就是它


def osa(script: str) -> str:
    return subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True).stdout.strip()


def click(x: float, y: float) -> None:
    for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        e = Quartz.CGEventCreateMouseEvent(None, t, (x, y), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetIntegerValueField(e, Quartz.kCGMouseEventClickState, 1)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
        time.sleep(0.05)


def key(code: int, flags: int = 0) -> None:
    for down in (True, False):
        e = Quartz.CGEventCreateKeyboardEvent(None, code, down)
        Quartz.CGEventSetFlags(e, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
        time.sleep(0.05)


def shot(out: str) -> None:
    subprocess.run(["screencapture", "-x", out], check=True)
    from PIL import Image
    im = Image.open(out)
    im.resize((im.width // 2, im.height // 2)).save(out)


def main(a: list[str]) -> None:
    cmd = a[0]
    if cmd == "activate":
        osa(f'tell application id "{APP_ID}" to activate')
    elif cmd == "shot":
        shot(a[1])
    elif cmd == "click":
        click(float(a[1]), float(a[2]))
        time.sleep(float(a[3]) if len(a) > 3 else 1.0)
        if len(a) > 4:
            shot(a[4])
    elif cmd == "file":
        osa(f'set the clipboard to (POSIX file "{a[1]}")')
    elif cmd == "text":
        # pbcopy 在无 LANG 的环境里会写空；用 osascript 按 UTF-8 读
        osa(f'set the clipboard to (read POSIX file "{a[1]}" as «class utf8»)')
        print("clipboard chars:", osa("length of (the clipboard as text)"))
    elif cmd == "paste":
        key(9, Quartz.kCGEventFlagMaskCommand)
        time.sleep(float(a[1]) if len(a) > 1 else 1.0)
        if len(a) > 2:
            shot(a[2])
    elif cmd == "bottom":
        Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                           Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (float(a[1]), float(a[2])), 0))
        for _ in range(40):
            Quartz.CGEventPost(Quartz.kCGHIDEventTap,
                               Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, -10))
            time.sleep(0.02)
        time.sleep(1.0)
        shot(a[3])
    elif cmd == "peek":
        ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
        c = [w for w in ws if w.get("kCGWindowOwnerName") == "ChatGPT" and w.get("kCGWindowLayer") == 0]
        c.sort(key=lambda w: -w["kCGWindowBounds"]["Width"] * w["kCGWindowBounds"]["Height"])  # 主窗口最大；小的是桌宠等浮窗
        if not c:
            raise SystemExit("ChatGPT window not found")
        subprocess.run(["screencapture", "-x", "-o", "-l", str(c[0]["kCGWindowNumber"]), a[1]], check=True)
        from PIL import Image
        im = Image.open(a[1])
        im.resize((im.width // 2, im.height // 2)).save(a[1])
    elif cmd == "front":
        print(osa('tell application "System Events" to get name of first process whose frontmost is true'))
    elif cmd == "clip":
        txt = osa("the clipboard as «class utf8»")
        open(a[1], "w", encoding="utf-8").write(txt)
        print("saved chars:", len(txt))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
