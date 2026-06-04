#!/usr/bin/env python3
import sys
import os
from PyQt6.QtWidgets import QApplication
from gui import MainWindow
from utils import load_config, save_config, PROXY_KEY


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_config()
    if PROXY_KEY not in cfg:
        cfg[PROXY_KEY] = 'http://127.0.0.1:7897'
        cfg['quark_cookie'] = cfg.get('quark_cookie', '')
        save_config(cfg)
    proxy = cfg.get(PROXY_KEY, '')
    if proxy:
        os.environ['HTTP_PROXY'] = proxy
        os.environ['HTTPS_PROXY'] = proxy
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
