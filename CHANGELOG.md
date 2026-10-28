# 更新日志

只记录 1.0.3 起的版本（更早的记录已移除）。旧版本的安装包与绿色版都保留在 `release\`，不删除。

---

## 1.1.0 — 2026-10-28

**修复**

- **同一天有 3 条以上任务时，第 3 条起显示不出来**：翻到任务更多的日期时，`_sync_today()` 只替换了任务行，外层卡片仍按上一天的高度摆着，超出的行被直接裁掉。改为每次同步后让布局签名失效并重排。
- **鼠标滚轮在卡片区域滚不动**：原来靠 canvas 的 `<Enter>` / `<Leave>` 动态 `bind_all`，但卡片是 canvas 的子窗口，指针一移进卡片就触发 `<Leave>` 把绑定解掉。改为常驻绑定 + 指针命中判断，卡片、按钮上都可滚动；备注输入框内保留文本自身滚动。

**产物**

- `release\PlanCheck-1.1.0-setup.exe`
- `release\PlanCheck-1.1.0-portable.zip`

---

## 1.0.4 — 2026-10-24

**修复**

- **换完图点「应用」又变回默认图**：判断要不要清空自定义图时，拿 `art_for_slot()` 的返回值去比。启用自定义图后它返回伪 key `custom:today`，永远不等于内置图 key，条件恒真，于是每次点应用都把刚设好的图删掉。改为跟对话框打开时该页选中的内置图 key 比较，只有明确改选别的内置图才清空。
- **点 × 要按两下才能退出**：关闭时遍历 `after info` 用 `root.after_cancel()` 取消，它会删掉 Tcl 命令却不从原控件的命令表销账；`root.destroy()` 级联销毁子控件时再删一次，抛 `TclError`，销毁中断、窗口留在屏幕上。改为 `root.tk.call("after", "cancel", aid)`，并给 `destroy()` 加兜底。
- **进度页换图会连带换掉启动画面**：两者原本共用图 key `gen_ring`。改为 5 个独立槽位（today / prog / cal / set / splash），老配置自动迁移。
- **模板稍作修改就导入失败**：`parse_date()` 里 `(text or "").strip()`，而 Excel 会把日期读成 `datetime` 对象，没有 `.strip()` 直接崩。新增 `_as_text()` 统一处理日期对象与 Excel 序列号；表头匹配支持全角、括号备注、同义词，命中阈值降到 1 列；`_read_xlsx` 读所有工作表；汇总行自动跳过；有表头却解析为空时退回无表头重试。
- **体积 40.4 MB → 29.6 MB**：排除 `pdfium.dll`（7 MB，仅 pdfplumber 页面预览用）与 Pillow 的 `_avif`（7.5 MB，程序只用 JPEG/PNG），以及一批用不到的 stdlib 与 PIL 扩展。

**产物**

- `release\PlanCheck-1.0.4-setup.exe`
- `release\PlanCheck-1.0.4-portable.zip`

---

## 1.0.3 — 2026-10-23

**修复**

- **双击后只有任务栏图标、界面出不来**：启动时把窗口设为 `alpha=0`，再靠一条 13 帧的 `after` 链拉回不透明。这条链在无控制台的 exe 上不执行，而 `_fade_in` 里是 `except: return`，链一断就再没有东西把 alpha 设回 1.0，窗口永久全透明。改为只降到 `0.88`，`_force_visible()` 无条件拉满，另加 0.8s / 1.5s 两道延时兜底。
- **「下载计划模板」只剩一个空界面**：`body` 先 `pack(expand=True)`、`footer` 后 `pack(side="bottom")`，内容一超高 footer 就被压成 1px 推出窗外。改为先建底部占位条，footer 往占位里放；窗口 760×560 → 780×620。
- **换背景图没反应**：`custom_art` 按页面 key 存、`art_path()` 按图 key 查，永远查不到；且 `clear_art_cache()` 没清页面底图缓存 `_PAGE_CACHE`，`page_art` 签名不变直接命中旧图。改为统一按图 key 存、两种缓存一起清、签名加入图文件指纹。
- **设置页点任何按钮都卡死**：旧胶囊按钮在 item 级 `<Enter>` 回调里 `delete()` 再重建同一批 item，指针没动、新 item 又触发 `<Enter>`，自激死循环。改为 widget 级 `<Enter>/<Leave>`，只重画不改控件几何，并加重入守卫。

**其它**

- 接上单实例锁 `InstanceLock`，双击多次不会再起多个进程（`--allow-multi` 可关）。
- `apply_art_change("splash")` 不再重建页面，只提示「下次启动生效」。
- 版本号 1.0.3。
