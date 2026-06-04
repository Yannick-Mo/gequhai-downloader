# 歌曲海批量下载工具

基于 PyQt6 的 GUI 桌面工具，从 [gequhai.com](https://www.gequhai.com) 搜索并批量下载歌曲。

## 功能

- 搜索歌曲（最多 15 条结果）
- 勾选后批量串行下载
- 高品质优先走夸克网盘（转存到账号后下载）
- 夸克失败自动降级低品质（kuwo.cn）
- 自动下载歌词（.lrc）和封面（.jpg）
- 统一文件名 `标题-歌手.*`
- 已下载歌曲灰色标记，不重复下载
- Cookie 和下载路径持久化存储

## 依赖

- Python >= 3.10
- PyQt6 >= 6.5
- requests

## 快速开始

```bash
pip install PyQt6 requests
python main.py
```

## 使用说明

1. **代理**：程序默认走 Clash 代理 `127.0.0.1:7897`，可在 `config.json` 中修改 `proxy` 字段
2. **夸克 Cookie**：首次启动弹出输入框
   - 打开 https://pan.quark.cn
   - F12 → Console → 输入 `document.cookie` → 复制整段粘贴
   - 勾选"记住 Cookie"可持久化
3. **搜索**：输入关键词回车或点搜索
4. **下载**：勾选歌曲 → 点"下载选中"或"下载全部"

## 项目结构

```
gequhai-downloader/
├── main.py          # 入口
├── gui.py           # PyQt6 界面
├── manager.py       # 串行下载队列引擎
├── gequhai.py       # 站点抓取（搜索、页面解析、低品质降级）
├── quark.py         # 夸克网盘 API（转存→下载）
├── utils.py         # 工具函数（配置/历史、下载、重试）
├── .gitignore
└── README.md
```

## 免责声明

本工具仅用于学习和研究，请勿用于商业用途。下载的歌曲请于 24 小时内删除。
