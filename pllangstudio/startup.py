"""啟動耗時：從行程建立（使用者雙擊）算起，寫進事件紀錄，使用者可以在事件檢視器自己查看。"""

import sys
import time

_IMPORTED = time.time()  # 取不到行程建立時間時的備案


def process_start() -> float:
    """行程建立的時間（time.time() 的秒數），包含 Python 與 Qt 載入的時間。"""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        created, _exit, _kernel, _user = (wintypes.FILETIME() for _ in range(4))
        if k32.GetProcessTimes(k32.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(_exit),
                               ctypes.byref(_kernel), ctypes.byref(_user)):
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime  # 從 1601 年起算，單位 100 奈秒
            return ticks / 10_000_000 - 11_644_473_600
    return _IMPORTED


def summary(window_seconds: float, load_seconds: float) -> str:
    return (f"啟動耗時：開啟視窗 {window_seconds:.2f} 秒，載入語言檔 {load_seconds:.2f} 秒，"
            f"合計 {window_seconds + load_seconds:.2f} 秒")
