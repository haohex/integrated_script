# 快速开始

本指南以“当前程序实际功能”为准，覆盖安装、启动、打包与常用配置。

## 1. 环境准备

- Python 3.8+
- Windows / Linux / macOS

安装依赖：

```bash
pip install -r requirements.txt
```

或开发模式：

```bash
pip install -e .
```

## 2. 启动方式

交互式菜单为主入口：

```bash
# 方式一：直接运行
python main.py

# 方式二：安装后使用命令
integrated-script
```

常用参数：

```bash
integrated-script --config path/to/config.yaml
integrated-script --log-level DEBUG
integrated-script --build
```

说明：命令行参数用于配置/日志/打包辅助，核心功能均在交互式菜单内。

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
pip install pyinstaller
python build_exe.py
```

产物位于 `dist/` 目录。

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
pip install -r requirements.txt
```

### OpenCV 读取失败

使用菜单中的“修复 OpenCV 读取错误的图像”。

### 需要静默或更详细日志

```bash
integrated-script --quiet
integrated-script --verbose
```

---

如需更详细说明，见 `README.md`。
