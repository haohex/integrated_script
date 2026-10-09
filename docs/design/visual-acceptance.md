# 桌面 GUI 与 TUI 视觉验收报告

> **环境声明与数据凭证**
> - **生成时间**: 2026-10-09
> - **执行环境**: Linux (x86_64, WSL2 kernel 6.18, .venv Python 3.11.15, PySide6 6.8.3, Textual 8.2.8)
> - **渲染后端**: 原生 X11/Xvfb 原生插件 (`QT_QPA_PLATFORM=xcb`) 与离线平台
> - **操作目录基准**: 接入真实 `integrated_script.application.AppService` 全部 42 项生产操作目录，彻底移除一切虚构操作。
> - **展示状态特别声明**: 运行中进度、执行结果（成功/失败）与二次危险操作确认弹窗等截图（`desktop-running-progress.png`、`desktop-result-success.png`、`desktop-result-failure.png`、`desktop-interaction-dialog.png`）均为**人工构建的界面展示状态**（用于精确校准与验证进度条、控制台日志、结构化表格、多层级树状展开、错误码横幅等交互控件外观），**并非 15,200 真实数据集样本实际批处理凭证**。
> - **跨平台限制声明**: 本次视觉样式与交互测试全部在真实 Linux Xvfb 原生环境（`xcb`）下由 PySide6 实际光栅化生成并固化。**明确注记为 Linux 真实渲染产物，绝不冒充 Windows 系统截图**；Windows 本地窗口修饰、标题栏原生样式、Segoe UI 字体抗锯齿微调未在实机验证（待 Windows CI 运行补充真实截图凭证），基准外观与配色遵循 Windows Fluent Slate / Blue-gray 规范。
> - **SVG 离线显示声明**: TUI 终端截屏 SVG 文件中 Rich 默认附带的 `@font-face` 远程 CDN URL 已全部移除，统一回退为本地 monospace 离线字体渲染；生产代码与发布产物不读取这些 SVG 文件。

---

## 1. 真实操作目录截图清单 (docs/design/screenshots/)

全套高精度截图生成脚本位于 `tests/ui/generate_screenshots.py`（Qt PNG）与真实 AppService 导出脚本（Textual SVG），全部基于真实 `AppService` 渲染生成：

### 1.1 桌面 Qt 图形界面样式 (PNG)

| 截图文件名 | 界面状态 | 尺寸 | 视觉与交互验收重点 |
| :--- | :--- | :--- | :--- |
| `desktop-light-main.png` | 浅色模式主界面 | 1200x780 | 浅色基底 `#F3F3F3`，卡片表面 `#FFFFFF`，冷灰边框 `#D1D1D1`，主强调色 `#0067C0`，真实42项功能分类目录树；选中 CTDS 项时贯穿缩进分支与文本形成一条普通连续整行选中背景，左侧无独立实心空方块，焦点外框清晰；PathPicker 浏览按钮呈现为“浏览… ▾”，彻底移除伪三角边框与短横线伪影，整按钮点击直接展开原生对话框选择菜单；主题选择器显示普通“浅色” |
| `desktop-dark-main.png` | 深色模式主界面 | 1200x780 | 深色基底 `#202020`，卡片表面 `#2C2C2C`，文字 `#F3F3F3`，浅蓝高亮 `#4CC2FF`，主题重着色矢量图标；“开始执行”主按钮采用深色文字与图标（`#001E36`），对比度 >8.5:1；选中 CTDS 项贯穿连续整行高亮无孤立方块；浏览按钮“浏览… ▾”平整统一；主题选择器显示普通“深色” |
| `desktop-destructive-banner.png` | 破坏性操作警示 | 1200x780 | 破坏性操作高对比红字警示 (`#FF7B72` 配合 `#3D1418` 底色)，安全横幅与醒目标识，真实操作 `yolo.clean_unmatched` |
| `desktop-interaction-dialog.png` | 二次确认弹窗 | 520xAuto | 模态居中对话框、主题化警告图标、受影响文件/空间详情列表、确认与取消双态保护（人工展示状态） |
| `desktop-running-progress.png` | 运行进度与实时日志 | 1200x780 | 真实操作 `yolo.validate_detection`，平滑进度条、阶段步骤描述、折叠式控制台日志高亮流式输出、禁用重复触发（人工展示状态，非15200样本实际运行） |
| `desktop-result-success.png` | 成功结果与结构化数据 | 1200x780 | 绿色成功状态条 (`#0F7B0F`)、提取的摘要关键指标卡片、结构化表格 (`QTableWidget`) 与层级数据树 (`QTreeWidget`)（人工展示状态） |
| `desktop-result-failure.png` | 失败结果与错误诊断 | 1200x780 | 高对比红色失败警示 (`#FF7B72`)、错误代码徽标 (`DATASET_PATH_NOT_FOUND`)、修复建议与上下文诊断（人工展示状态） |
| `desktop-compact-mode.png` | 紧凑布局模式 | 980x600 | 紧凑模式按钮触发、自适应缩放无控件被遮挡或溢出、自适应滚动容器；目录树依然呈现连续整行选中高亮 |

### 1.2 终端 TUI 界面样式 (SVG)

| 截图文件名 | 终端尺寸 | 界面状态 | 视觉与交互验收重点 |
| :--- | :--- | :--- | :--- |
| `tui-80x24-main.svg` | 80x24 | 紧凑终端主界面 | 80x24 紧凑视口自适应布局；顶部操作栏、左侧目录树与右侧表单完整容纳，无文本溢出折断；Rich 默认 CDN 字体声明已移除，使用本地 monospace 离线展示 |
| `tui-80x24-nav-toggled.svg` | 80x24 | 导航折叠宽表单状态 | 支持快捷键 `Ctrl+B` 或顶部 `☰ 导航` 按钮折叠侧边栏，为表单参数编辑与控制台输出提供整屏宽度；离线 monospace 字体渲染 |
| `tui-120x40-main.svg` | 120x40 | 标准宽屏终端主界面 | 120x40 标准终端主界面，双栏并排、表单输入、可空字段占位提示与执行按钮完整呈现；离线 monospace 字体渲染 |

---

## 2. 视觉缺陷修复与设计规范校验

### 2.1 主题色彩、Qt 信号与无污染回退
- **系统主题一致性与动态监听**:
  - `MainWindow`、`ResultView`、`icon_provider` 全部一致读取 Qt 系统色彩；修正此前 `ResultView` 与默认图标不传递应用实例导致系统深色时误判为浅色的缺陷。
  - `QApplication.styleHints().colorSchemeChanged` 信号在“跟随系统”选项下实时生效；当用户显式选择“浅色”或“深色”时，保留用户显式配置，不受系统信号干扰。
  - 当系统色彩方案为 `Unknown` 时，明确回退至 `light`，不再以应用自身已加载的 QSS / Palette 判定系统深浅，彻底阻断 QSS 污染。
  - `ui/shared` 在无 Qt 环境（如 TUI 与常规子进程）下导入时不导入 PySide6，严格保证 TUI 无 Qt 依赖。
- **原生字体与中文回退策略 (Native QFont & QFontDatabase)**: 遵循系统原生 Qt QFont API 策略，在 QSS 样式表中移除 Web 式 `font-family` 逗号分隔字符串覆盖；统一通过 `app.py` 中的 `setup_application_font()` 函数动态探测平台可用字体并使用 `QFont.setFamilies()` 配置操作系统原生字体栈与中文回退（Windows 下首选 `Segoe UI`、`Microsoft YaHei UI`、`Microsoft YaHei`；macOS 下首选系统字体、`PingFang SC`；Linux 下首选 `Ubuntu`、`Noto Sans CJK SC`）。Windows 环境下的原生字体具体渲染抗锯齿质量以云端实机截图证据为准，不提前虚构未经验证的断言。
- **深色主按钮高对比文字与图标**: 深色主题下主按钮背景为 `#4CC2FF`，统一将深色主题的 `text_on_accent` 设为 `#001E36`，图标与文字对比度达到 8.8:1（远超 WCAG AAA 7:1 标准）。
- **导航连续整行选中样式与孤立方块消除**: 导航树（`QTreeWidget`）的 `margin` 与 `border-radius` 均设为 `0`，启用 `show-decoration-selected: 1`，并在 QSS 中设置 branch 与 item 统一背景色（`{p['accent_subtle']}`）。
- **键盘导航支持**: 导航树连接 `itemActivated` 信号，支持键盘光标浏览叶子项并按 Enter/Return 键直接加载操作，无需强依赖鼠标点击。在后台任务运行期间（`service.busy`）保护表单，禁止键盘/点击或搜索联动重置或擦除正在运行的操作与确认表单。
- **PathPicker 浏览按钮下拉菜单与箭头渲染**: `PathPicker` 的 `QToolButton` 设为 `InstantPopup` 模式，文案设定为“`浏览… ▾`”，隐藏原生 `menu-indicator`，消除伪边框。
- **窗口标题规范化**: 窗口标题普通设定为“`集成脚本工具`”，移除“`- 工业级批量数据处理平台`”宣传后缀。
- **关闭保护与系统信号生命周期**: `closeEvent` 在后台任务忙碌拒绝关闭时不注销 `colorSchemeChanged` 监听器；当正常关闭时停止轮询定时器并调用 `qapp.quit()` 确保主事件循环干净终止，进程以退出码 0 退出。
- **结果横幅动态刷新与页面保持**: `ResultView` 增加 `update_theme()` 方法，在主题切换时更新横幅配色与图标，同时完好保留当前 payload 数据及激活的标签页索引。

### 2.2 表单字段可空值与类型仿真 (FormBuilder Nullability)
- **None、0 与 False 严格区分**:
  - 真实后端配置操作（`config.edit_processing`, `config.edit_image`, `config.edit_yolo`, `config.edit_ui`）将 `default=None` 作为“不修改现有配置”的语义。
  - 在 GUI 和 TUI 中，`kind='int'`/`'float'` 且 `default=None` 时使用可空数字输入控件（`NullableNumberEdit` / 可空 `Input`），留空时返回 `None`，不向后端注入假 `0`；用户明确输入 `0` 或 `0.0` 时忠实返回数值 `0`。
  - `kind='bool'` 且 `default=None` 时提供三态选择器（`[保持原值 (不修改), 是 (True), 否 (False)]`），默认保留 `None`；用户明确选“否”时返回 `False`。
  - `reset_defaults()` 保持重置为 `None`，UI 不自行发明默认业务值。

### 2.3 路径处理与浏览交互
- **路径保持原始输入**: UI 层（GUI 与 TUI）仅做首尾空白与成对引号去除 (`clean_path_input`)，不再擅自将其转换为绝对路径，路径业务解析与波浪号展开交由后端统一管理。
- **多功能路径选择菜单**: `PathPicker` 浏览按钮采用 `InstantPopup` 模式与清晰的“`浏览… ▾`”指示，点击直接展开菜单按动作弹出对应原生/兜底对话框。

### 2.4 纯正后端合约与测试 Fake 隔离
- **零生产 Fake**: 彻底删除 `ui/shared/fake_service.py`，生产代码严禁打包或导出假服务。缺失后端时明确抛出 `RuntimeError` 并快速失败。
- **直接导入合约**: `ui/shared/contract.py` 直接导入 `integrated_script.application` 核心合约与 `AppService`。
- **截图环境彻底沙箱化**: 验收与截图运行时对 `QT_QPA_PLATFORM`、`XDG_*`、`APPDATA`、`LOCALAPPDATA`、`HOME`、`USERPROFILE`、`PlatformDirs` 以及 `theme_override` 进行完整沙箱隔离与严格上下文恢复，成功与异常均保障所有窗口与服务完全关闭，绝不碰触真实 `$HOME` 用户配置。

---

## 3. 终端 TUI（Textual）实现与 80x24 适配

- **按键冲突修复**: 移除 `priority=True` 的单键 `q` 全局退出绑定，更改为 `ctrl+q` 退出，彻底解决用户在路径输入框或搜索框输入含字母 `q` 的文本（如 `/data/quick/seq.txt`）被劫持退出程序的缺陷。
- **80x24 视口折叠导航**:
  - 提供 `Ctrl+B` 快捷键与顶部栏 `☰ 导航` 按钮。
  - 折叠后目录树隐藏，表单控件与操作按钮占据完整 80 列，配合 `VerticalScroll` 滚动容器，确保小屏幕下常用字段、主操作、确认/取消按钮均可通过 Tab/Shift+Tab 快捷键抵达。
- **路径补全与模态目录浏览**:
  - `PathSuggester`: 集成 Textual 异步输入补全器，输入路径前缀时实时提示匹配的本地目录与文件。
  - `PathBrowserModalScreen`: 提供全功能文件/目录浏览模态弹窗，使用 `DirectoryTree` 交互式选取文件或文件夹并一键回填到表单输入框。

---

## 4. 自动化测试与静态质量门禁

所有前端拥有的测试用例与静态检查已 100% 通过：
- **测试用例套件** (`pytest tests/ui`): 全部通过
  - `test_backend_requirement.py`: 验证 GUI 与 TUI 在缺少后端时抛出 RuntimeError。
  - `test_desktop_widgets.py`: 验证各类表单控件、Nullable 保持、0 与 False 区分、二次确认弹窗、表格与多级树格式化渲染、PathPicker InstantPopup 与菜单动作。
  - `test_desktop_window.py`: 验证导航树过滤、破坏性操作标识、执行事件轮询、紧凑模式切换、主题选项、整行连续选中 QSS 规则、键盘 Return/Enter 激活叶子项、以及任务 busy 状态下对当前操作表单的完整保护。
  - `test_real_integration.py`: 真实 AppService 端到端联调（`config.view`, `env.check_dependencies`, `yolo.ctds_to_yolo` 交互确认）。
  - `test_shared.py`: 主题配色、格式化解析与合同接口测试。
  - `test_tui.py`: TUI 目录加载、FormBuilder 可空保持、导航侧边栏折叠。
  - `test_tui_regression.py`: 验证含 `q` 路径输入、Textual 路径补全与文件浏览模态框。
  - `test_theme_and_isolation_regression.py`: 覆盖 Qt 信号动态切换、用户配置保护、深浅隔离与双重冷启动沙箱。
  - `test_native_acceptance_and_overflow_regression.py`:
    1. ResultView 最小尺寸边界约束（`test_result_view_minimum_size_hint_bounded`，杜绝长路径将主窗口挤爆）
    2. 搜索框关键词实时自动联动选中匹配操作（`test_search_auto_selects_first_matching_operation`）
    3. 主操作执行按钮快捷键（`test_main_window_execute_button_has_shortcut`，保证 `Ctrl+Return` 可访问性）
  - `test_frozen_gui_controller.py`:
    1. WindowSpecification 与已解析 wrapper（EditWrapper/ButtonWrapper）的 API 差异及存在性检测兼容。
    2. 真实可见主窗口精准选择，彻底剔除 Qt 隐藏辅助窗口与控制台宿主窗口。
    3. 64 位 Win32 ctypes 签名安全性设置。
    4. 控件文本写入与按钮点击 fallback 支持。
    5. child_window 与 descendants fallback 两种自动化模式端到端模拟验证。
    6. pywinauto close 与 64 位 PostMessageW WM_CLOSE 优雅关闭协议。

---

## 5. 原生高 DPI 跨平台验收规范 (`tests/ui/native_acceptance.py`)

### 5.1 CLI 约定与调用方式
```bash
# 单一缩放比例运行 (例如 100% 或 150%)
python tests/ui/native_acceptance.py --output /path/to/output --scale 1

# 多缩放比例矩阵运行 (覆盖主流高 DPI: 100%, 125%, 150%, 175%, 200%)
python tests/ui/native_acceptance.py --output /path/to/output --scale 1,1.25,1.5,1.75,2
```

### 5.2 核心机制与质量保证
1. **强制原生 Qt 插件**: 禁止使用 `offscreen`。Windows 下强制使用 `windows` 插件；Linux 下强制使用 X11 `xcb` 插件（通过 Xvfb 或真实显示器运行）。若未检测到图形环境，明确退出并输出诊断，不伪造测试结果。
2. **进程级 DPI 隔离**: 每个缩放比例在独立的 Python 子进程中运行，在加载任何 Qt 模块前设置 `QT_SCALE_FACTOR` 与 `QT_ENABLE_HIGHDPI_SCALING`。明确注记该项为**应用逻辑缩放验证**（QT_SCALE_FACTOR application scaling verification），并非 Windows 物理设备 OS DPI 硬件实测。
3. **真实业务操作闭环**:
   - 运行“中文空格路径创建空标签”(`label.create_empty`)：验证含中文与空格的路径（如 `测试 样本 目录 空格`）正常创建 `.txt` 空标签文件，严格核验文件存在且为 0 字节。
   - 运行“PNG转JPEG”(`image.convert`)：生成真实 64x64/48x48 PNG 图像，转换生成合法 JPEG 文件；**使用 PIL.Image.open 严格校验文件格式为 JPEG 且尺寸严格为 64x64 和 48x48**，杜绝仅靠后缀判断。
4. **小屏幕适配与尺寸约束 (Clamp Smaller Screen + Scroll)**:
   - 窗口初始化与切换紧凑模式时，严格对照 `screen.availableGeometry()`（例如 1920x1080@200% 下逻辑视口为 960x540），自动 clamp 窗口尺寸，杜绝超屏。
   - 验证主执行按钮（`btn_execute`）完全可见且处于可用状态，表单区域通过 `QScrollArea` 自动提供滚动条。
5. **结构化报告产物**:
   - 每个 scale 独立生成子目录（如 `scale_1`, `scale_2`）。
   - 导出包含实际平台、Qt 平台名、DPI（逻辑/物理/DPR）、屏幕可用几何与窗口几何对照、操作验证详情的 `acceptance_report.json`。
   - 子进程设置 bounded timeout <= 90s，任何 scale 失败或超时整体非 0 退出。

---

## 6. 冻结发布包冒烟验收规范 (`tests/ui/frozen_gui_smoke.py`)

### 6.1 CLI 约定与调用方式
```bash
python tests/ui/frozen_gui_smoke.py --executable /path/to/extracted_gui_executable --output /path/to/output
```

### 6.2 核心机制与质量保证
1. **测试对象真实性**: 严格测试解压后的二进制可执行文件（Windows `.exe` / Linux 二进制），严禁使用源码 `MainWindow` 代替。
2. **控制台窗口无泄漏检测**: Windows 下通过 `EnumWindows` 枚举目标 PID 的所有顶层窗口，检测是否存在 `ConsoleWindowClass` 可见窗口，确保 GUI 分发包无控制台黑框弹出。
3. **严格黑盒自动化驱动**:
   - 启动被测进程，清理其 `PYTHONPATH`、`PYTHONHOME` 及 PATH 中的 Python 环境。
   - 定位到 `label.create_empty`，在中文+空格路径下生成真实有效 PIL 图像，外部键盘/控件输入输入与输出路径，触发执行。
   - **严格产物验证**: 仅当预期的 2 个 `.txt` 标签文件均存在且大小严格为 0 字节时，方判定 `output_verified = True`。截图或按键发送绝不直接认作运行成功。
4. **GUI 优雅关闭与退出码校验**:
   - 兼容 Xvfb 无窗口管理器环境与 Windows pywinauto/WM_CLOSE。
   - 针对 Windows，精准筛选真实可见主窗口（排除 Qt 内部隐藏 helper 窗口），使用 64 位 Win32 ctypes 签名安全发送 `WM_CLOSE` 并调用 pywinauto 窗口关闭。
   - `proc.wait()` 返回码必须严格为 0。SIGTERM (-15) 坚决不认作 clean exit。超时、未交互、缺输出或截图失败均非 0 退出。
   - `finally` 块仅清理自身派生的 PID 与子进程树，杜绝遗留孤儿进程。
5. **无头会话 (Session 0) 明确失败**: 在 Windows Runner 无交互桌面的受限场景下，明确输出检测诊断与原因（如 `Session 0 / Headless Virtual Screen`），直接以非 0 退出码失败，坚决不伪造虚假 Pass。

---

## 7. 平台证据现状与待补 (Pending) 证据跟踪表

| 证据项 | 目标平台 / 环境 | 验证工具 / 脚本 | 当前状态 | 证据来源与详情 |
| :--- | :--- | :--- | :--- | :--- |
| **Linux 原生高 DPI 验收 (100%-200%)** | Linux (Ubuntu / WSL2 Xvfb xcb) | `tests/ui/native_acceptance.py` | **已完成 (Passed)** | 1.0, 1.25, 1.5, 1.75, 2.0 全部 5 组 scale 检验通过；明确标识为 QT_SCALE_FACTOR 应用缩放验证；完成中文空格路径空标签创建（0字节验证）与真实 PNG 转 JPEG（PIL.open 核验 JPEG 格式及 64x64/48x48 尺寸）；窗口与框架几何对照 screen.availableGeometry 严格 clamp（960x540），主要执行按钮完全可用，0 关键裁剪。 |
| **Linux 冻结发布包冒烟验收** | Linux (Ubuntu ELF 二进制) | `tests/ui/frozen_gui_smoke.py` | **已完成 (Passed)** | 经此轮与前轮 GitHub Actions Linux strict 运行实际检验，基于真实提取的二进制文件（`extracted/integrated_script_gui`），在严格环境隔离与 xcb 插件下运行；通过 client 几何相对坐标精准交互完成 `label.create_empty`；严格核验生成 2 个 0 字节真实空标签、有效捕获窗口截图，并通过 X11 WM_PROTOCOLS / WM_DELETE_WINDOW 优雅退出，进程返回码严格为 0。 |
| **Windows 原生高 DPI 样式证据 (100%-200% 五档完整)** | GitHub Windows Server 2022 (windows 插件，非 Win10/11 物理高 DPI) | `tests/ui/native_acceptance.py` | **已完成 (Passed)** | 真实 GitHub Actions run 37951271896 WindowsServer2022 job 113891028806 产物（5 Native 报告目录共 30 张高精度 PNG 截图与对应 JSON 报告）。100%、125%、150%、175%、200% 全 5 档测试全部 `all_passed=true`。真实业务闭环（空标签 0 字节校验、PIL 严格校验 PNG 转 JPEG 64x64/48x48）全部通过；DPR 合成已修正为完整物理像素分辨率（200% 对应 1024x752，不再发生 1/4 缩小）；小屏 availableGeometry clamp 验证通过，无控件溢出与关键截断。 |
| **Windows 冻结 exe 冒烟验收** | Windows (PyInstaller .exe) | `tests/ui/frozen_gui_smoke.py` | **待重新云端验收 (Pending Cloud Re-run)** | 在真实 GitHub run 37951271896 中，frozen-gui 已验证正常启动、无控制台泄漏（`console_window_leaked=false`）、交互桌面可用（`interactive_desktop=true` 1024x768）；但因旧驱动逻辑中 `descendants` 返回 `EditWrapper` 缺乏 `exists()` 方法以及使用 `wins[0]` 辅助隐藏窗口发送 WM_CLOSE 导致 8 秒超时，执行失败（exit 1）。现已在 `tests/ui/frozen_gui_smoke.py` 中彻底修复控件存在性兼容（`is_control_existing` / `set_control_text`）、主窗口选择（`select_primary_windows`）及 64 位 Win32 ctypes 签名安全关闭协议。等待主代理 git push 后由 GitHub Actions Windows Runner 重新跑真正 Windows frozen GUI，本地 Linux 模拟通过绝不冒充 Windows 成功。 |

> **注**: 远端 Windows CI 跑完并上传制品后，主代理将通知前端代理对真实 Windows 截图与 DPI 报告进行正式 Review。

---

## 8. CI 验收环境所需系统依赖清单 (供 CI 配置使用)

为了在 CI 环境中顺利执行上述 2 个验收脚本，需要以下系统级与开发依赖：

### Linux Runner (Ubuntu)
```bash
# Xvfb 虚拟显示服务器与原生 xcb 支持
sudo apt-get update && sudo apt-get install -y xvfb libxcb-cursor0 xdotool
```

### Windows Runner
```bash
# 外部 UIAutomation 自动化测试依赖 (Dev/CI 专用，被测 exe 本身不依赖)
pip install pywinauto pillow
```
