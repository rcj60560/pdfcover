# Word→Markdown

`.docx` → GitHub 风格 Markdown，subprocess 调 [pandoc](https://pandoc.org/) 实现。

## 依赖

- pandoc ≥ 3.x（`winget install --id JohnMacFarlane.Pandoc`）

## 用法

```bash
python word2md_cli.py 需求说明书.docx                    # → 同目录 需求说明书.md + 图片和附件/
python word2md_cli.py 图片和附件/说明书.docx              # → 上一级 说明书.md，图片并入 图片和附件/
python word2md_cli.py 说明书.docx -o out/说明书.md        # 指定输出
python word2md_cli.py 说明书.docx --media-dir assets      # 指定图片目录
```

不带参数运行则提示输入路径，可直接把文件拖进窗口。程序化调用用 `word2md_core.convert()`。

## 默认行为

- **输出**：docx 同目录同名 `.md`；若 docx 躺在 `图片和附件/` 里，md 放上一级（对齐 devdocs 归档结构）
- **图片**：抽到 md 同目录的 `图片和附件/`（无图不建目录）；拍平 pandoc 强加的 `media/` 子层，`<img>` 改写成 `![]()`
- **表格**：简单表格转 GFM 管道表，复杂表格（合并单元格等）降级为 HTML 表——渲染正常且不丢数据（`-t gfm` 保留 raw_html 的原因）
- **中文**：`--wrap=none`，不会被 72 列硬换行切碎
- 老版 `.doc` 不支持，提示先另存为 `.docx`

## 测试

`tests/test_word2md.py`（pandoc 未安装时集成用例自动跳过）。
