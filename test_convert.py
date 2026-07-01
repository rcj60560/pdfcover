"""测试 PDFCover 转换功能"""
from pdfcover import convert_folder
import sys

# 设置 UTF-8 编码输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 转换当前目录
folder = "D:/Users/28975/PycharmProjects/pdfcover/pdfcover"

print(f"正在扫描文件夹: {folder}")
print("=" * 60)

results = convert_folder(folder, output_suffix="_ocr")

print("\n转换结果:")
print("=" * 60)

for r in results:
    status_icon = {
        "success": "[OK]",
        "failed": "[FAIL]",
        "skipped": "[SKIP]"
    }.get(r["status"], "[?]")

    print(f"{status_icon} {r['source']}")
    if r["status"] == "success":
        print(f"  -> {r['output']}")
    elif r["status"] == "failed":
        print(f"  错误: {r.get('error', 'Unknown')}")
    else:
        print(f"  (已跳过)")

# 统计
success_count = sum(1 for r in results if r["status"] == "success")
failed_count = sum(1 for r in results if r["status"] == "failed")
skipped_count = sum(1 for r in results if r["status"] == "skipped")

print("\n" + "=" * 60)
print(f"总计: {len(results)} 个文件")
print(f"成功: {success_count} | 失败: {failed_count} | 跳过: {skipped_count}")
