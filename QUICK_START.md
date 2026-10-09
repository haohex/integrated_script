# 快速开始

本指南以“当前程序实际功能”为准，覆盖安装、启动、打包与常用配置。

普通用户直接从 [发布页](https://github.com/haohex/integrated_script/releases/latest) 下载对应平台的软件包，无需安装 Python。Windows 客户端选择 `windows-x64-gui.zip`，完整解压后打开 `integrated_script_gui.exe`；Linux 客户端选择 `linux-x64-gui.tar.gz`。终端界面选择 `tui` 包。保留 `_internal` 目录。

## 1. 环境准备

- Python 3.11+
- 本次离线包：Windows x64 / Ubuntu 22.04、24.04 x64 / Linux ARM64 TUI；不提供 macOS 包

安装依赖（默认终端界面，不含 Qt）：

```bash
pip install -r requirements-runtime.txt
```

或安装/开发模式：

```bash
pip install -e .            # TUI + 核心
pip install -e .[gui]       # 需要 Qt 桌面界面时
pip install -e .[dev,gui,dev-ui]   # 开发 + 界面测试
```

## 2. 启动方式

```bash
# 默认：终端界面（TUI）
python main.py

# 桌面界面（需安装 [gui]）
python main.py --gui

# 旧交互式命令行（兼容回退）
python main.py --legacy-cli

# 安装后
integrated-script            # 默认 TUI
integrated-script-gui        # GUI 专用入口（Windows 无控制台窗口）
integrated-script --legacy-cli
```

常用参数：

```bash
integrated-script --config path/to/config.yaml
integrated-script --log-level DEBUG
integrated-script --build          # 构建默认 TUI 产物
```

说明：配置/日志写入用户目录；当前目录存在旧配置时首次使用会提示导入，原文件保留。

## 3. 主要功能入口（菜单）

- YOLO 数据集处理
  - CTDS 转 YOLO / YOLO 转 CTDS
  - YOLO 转 X-label（自动识别检测/分割）
  - X-label 转 YOLO（自动识别检测/分割）
  - 目标检测/分割数据集验证
  - 清理不匹配文件（支持试运行）
  - 合并多个数据集（同类型/不同类型）
- 图像处理
  - 格式转换 / 尺寸调整 / 压缩
  - 修复 OpenCV 读取失败图像
  - 获取图像信息与统计
- 文件操作
  - 数据集重命名（images/labels 同步）
  - 按扩展名组织文件
  - 递归删除 JSON
  - 批量复制 / 移动
- 标签处理
  - 创建空标签
  - 翻转/过滤标签
  - 删除空标签或指定类别标签
- 配置管理
  - 查看 / 修改 / 加载 / 保存 / 重置
- 环境检查与配置（非 EXE 环境显示）

## 4. 构建可执行文件

```bash
# TUI 产物（不含 Qt）
pip install -r requirements-build.txt
python build_exe.py --mode tui     # 终端界面（默认）

# GUI 产物（安装固定版本 PySide6==6.8.3）
pip install -r requirements-build-gui.txt
python build_exe.py --mode gui     # 桌面界面（Windows 无控制台）
python build_exe.py --mode all     # 依次构建两者
```

产物位于 `dist/integrated_script/`（TUI）与 `dist/integrated_script_gui/`（GUI）。
详见 `docs/offline-deployment.md`。

## 5. 配置文件

默认配置文件：`config/default_config.yaml`

可在交互式菜单中：
- 查看当前配置
- 修改配置
- 保存到新配置文件
- 重置为默认配置

## 6. 常见问题

### 依赖未安装

```bash
pip install -r requirements-runtime.txt
```

### TUI 无法启动 / 提示缺少终端组件

确认已安装运行期依赖（含 `textual`）：

```bash
pip install -r requirements-runtime.txt
```

仍不可用时可用旧界面回退：`integrated-script --legacy-cli`。

### GUI 无法启动

Qt 桌面界面需要显式安装：

```bash
pip install -e .[gui]
```

Linux 上还需要系统图形依赖，见 `docs/offline-deployment.md`。

### OpenCV 读取失败

使用菜单中的“修复 OpenCV 读取错误的图像”。

### 需要静默或更详细日志

```bash
integrated-script --quiet
integrated-script --verbose
```

---

如需更详细说明，见 `README.md`。
