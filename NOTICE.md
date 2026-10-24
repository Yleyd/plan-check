# 版权与来源说明

## 程序本体

Plan check 的源代码由本项目编写，采用 MIT 许可（见 `LICENSE`）。

## 内置背景图

`assets/default/` 下的 6 张图（`gen_night.jpg`、`gen_ring.jpg`、`gen_hat.jpg`、
`gen_clash.jpg`、`gen_flame.jpg`、`gen_eye.jpg`）全部由 `tools/genart.py`
用 numpy + Pillow 程序化生成，是纯数学渐变、径向光晕、噪声与几何图形的合成结果，
不含任何第三方摄影、插画或视频素材，可随本项目自由分发、修改、商用。

生成方式可复现：

```bash
python tools/genart.py
```

脚本会重新写出这 6 张 1920×1080 的 JPEG，输出目录为 `assets/default/`。

## 应用图标

`assets/icon.png` 与 `assets/icon.ico`（羽毛笔）由项目作者使用 AI 图像工具生成，
再处理成多尺寸图标。生成式输出通常不构成对他人作品的复制，
但仍建议在商业使用时自行复核所用工具的服务条款。

## 已移出仓库的素材

`assets/original/` 目录里保存的是 1.0.1 及更早版本内置的 6 张插画，
来源是网络视频截图，**不随本项目分发**，也不包含在安装包与绿色版中。
该目录已写入 `.gitignore`，仅在本机保留用于对照。

如果你从别处拿到了这个目录里的图，请自行确认其授权情况。

## 第三方库

- Pillow — HPND License
- openpyxl — MIT
- python-docx — MIT
- pdfplumber / pdfminer.six — MIT
- Inno Setup（仅用于生成安装包，不随程序分发）— Inno Setup License
- PyInstaller（仅用于打包，不随程序分发）— GPL with exception

## 字体

界面使用系统自带的「Microsoft YaHei UI」（微软雅黑），不随程序分发字体文件。
