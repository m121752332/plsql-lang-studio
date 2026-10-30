import time

from pllangstudio import startup


def test_process_start_is_before_now():
    """起算點是行程建立的時間（使用者雙擊時），比匯入模組的時間更早。"""
    start = startup.process_start()
    assert time.time() - 24 * 3600 < start <= time.time()


def test_summary_shows_window_load_and_total_seconds():
    assert startup.summary(1.234, 0.456) == "啟動耗時：開啟視窗 1.23 秒，載入語言檔 0.46 秒，合計 1.69 秒"
