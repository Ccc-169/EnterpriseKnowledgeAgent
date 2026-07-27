"""查看 QA Cache 缓存表内容"""
from core.database import get_db

conn = get_db()
rows = conn.execute(
    "SELECT id, question, substr(answer,1,100) as ans_preview, "
    "kb_version, hit_count, created_at "
    "FROM qa_cache ORDER BY id"
).fetchall()

print(f"qa_cache 记录总数: {len(rows)}")
print("=" * 100)
for r in rows:
    print(f"\n[id={r['id']}]  hit={r['hit_count']}  kb={r['kb_version']}")
    print(f"  时间: {r['created_at']}")
    print(f"  问题: {r['question']}")
    print(f"  答案: {r['ans_preview']}...")

conn.close()
print("\n" + "=" * 100)
print("数据库文件: data/hngd.db  (表名: qa_cache)")
