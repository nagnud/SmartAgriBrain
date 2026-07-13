import json
import os
import re

# 指向你刚刚保存的百科源文件
INPUT_FILE = "raw_encyclopedia.json"
OUTPUT_FILE = "../backend_server/knowledge_base/agri_encyclopedia.json"


def clean_encyclopedia_data():
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到 {INPUT_FILE}，请确保你已经把包含埃及棉等词条的 JSON 数据保存在了这个文件里。")
        return

    cleaned_entries = []
    for item in raw_data:
        title = item.get("title", "").strip()
        # 清除原文中多余的换行符和制表符，压缩成紧凑的纯文本以节省大模型 Token
        detail = item.get("detail", "")
        detail_clean = re.sub(r'\s+', ' ', detail).strip()
        url = item.get("url", "")

        # 组装成大模型最易于检索的平铺结构
        entry = {
            "entity_name": title,
            "description": detail_clean,
            "source_url": url
        }
        cleaned_entries.append(entry)

    # 写入最终的知识库目录
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cleaned_entries, f, ensure_ascii=False, indent=4)

    print(f"✅ 知识库清洗完毕！成功将 {len(cleaned_entries)} 条专业词条写入 {OUTPUT_FILE}")


if __name__ == "__main__":
    clean_encyclopedia_data()