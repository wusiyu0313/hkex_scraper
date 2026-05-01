# HKEX IO Scraper

## 功能
- 按月份（`YYYY-MM`）批量抓取 HKEX 新上市申请文件中的 `Industry Overview / 行业概览`。
- 命名格式：`{委托公司}_{公司名称}_{业务}_CN|EN.pdf`，业务字段固定为中文行业分类。
- 输出结构：

```text
output/
  2026-04/
    CN/
    EN/
    待人工确认/
```

- 若无真实 `Industry Overview / 行业概览`，状态标记为 `manual_review`，文件进入 `待人工确认/`。

## 安装
```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## CLI 运行
```bash
python main.py --month 2026-04
```

可选限制抓取数量（CLI 专用）：
```bash
python main.py --month 2026-04 --limit 10
```

## UI 运行（Flet 桌面）
```bash
python ui_app.py
```

UI 支持：
- 月份输入（`YYYY-MM`）
- 本月公司总数
- 实时进度（例如 `41/91`）
- 状态计数（done/partial/failed/manual_review）
- 开始/停止（停止在当前公司完成后生效）

## 打包分发（开箱即用）

### Windows
```powershell
./scripts/build_windows.ps1
```

### macOS (Apple Silicon arm64，本机打包)
```bash
bash ./scripts/build_macos.sh
```

### macOS (推荐：GitHub Actions 云端打包)
仓库已提供工作流：[build-macos.yml](.github/workflows/build-macos.yml)

操作：
1. 推送代码到 GitHub。
2. 打开 `Actions` -> `Build macOS App` -> `Run workflow`。
3. 构建完成后下载 artifact：`HKEXIOScraper-macos-arm64.zip`。
4. 发给同事解压后直接运行 `HKEXIOScraper.app`。

构建后产物在 `dist/`（本地）或 GitHub Actions artifact（云端）。

## 测试
```bash
python -m pytest -q
```
