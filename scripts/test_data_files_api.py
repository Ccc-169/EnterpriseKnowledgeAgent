"""集成测试：data-files API 端点
将所有结果同时打印到 stdout 和文件，方便在 Windows PowerShell 中查看。
"""
import sys
sys.path.insert(0, '.')
import os
os.environ['DATA_DIR'] = './data/files'

import io
import time as _time
from jose import jwt
from fastapi.testclient import TestClient
import api

SECRET = 'hngd-knowledge-agent-secret'
ALG = 'HS256'
ADMIN_TOKEN = jwt.encode({'sub':'1','username':'admin','role':'admin','display_name':'Admin','exp': int(_time.time())+3600}, SECRET, algorithm=ALG)
USER_TOKEN  = jwt.encode({'sub':'2','username':'user', 'role':'user', 'display_name':'User', 'exp': int(_time.time())+3600}, SECRET, algorithm=ALG)
H_ADMIN = {'Authorization': f'Bearer {ADMIN_TOKEN}'}
H_USER  = {'Authorization': f'Bearer {USER_TOKEN}'}

client = TestClient(api.app)
xlsx_bytes = b'PK\x03\x04 fake xlsx content for test'

def line(s):
    print(s, flush=True)

results = []
def check(name, ok, detail=''):
    results.append((name, ok, detail))
    mark = '✅' if ok else '❌'
    line(f'  {mark} {name} - {detail}')

line('=' * 70)
line('集成测试：data-files API')
line('=' * 70)

# 1. 未登录
r = client.get('/api/admin/data-files')
check('未登录拒绝', r.status_code == 401, f'HTTP {r.status_code}')

# 2. admin list
r = client.get('/api/admin/data-files', headers=H_ADMIN)
check('管理员列表', r.status_code == 200, f'HTTP {r.status_code}')

# 3. upload xlsx (clean)
r = client.post('/api/admin/data-files/upload', headers=H_ADMIN,
               files={'file': ('fresh_test.xlsx', io.BytesIO(xlsx_bytes), 'application/vnd.openxmlformats')},
               data={'overwrite':'false'})
ok = r.status_code == 200 and r.json().get('name') == 'fresh_test.xlsx'
check('上传新文件', ok, f'HTTP {r.status_code} body={r.json() if r.status_code==200 else r.text[:80]}')

# 4. upload 同名 (期望 409)
r = client.post('/api/admin/data-files/upload', headers=H_ADMIN,
               files={'file': ('fresh_test.xlsx', io.BytesIO(xlsx_bytes), 'application/vnd.openxmlformats')},
               data={'overwrite':'false'})
check('同名拒绝 (overwrite=false)', r.status_code == 409, f'HTTP {r.status_code}')

# 5. 覆盖
r = client.post('/api/admin/data-files/upload', headers=H_ADMIN,
               files={'file': ('fresh_test.xlsx', io.BytesIO(xlsx_bytes), 'application/vnd.openxmlformats')},
               data={'overwrite':'true'})
ok = r.status_code == 200 and r.json().get('overwritten') is True
check('覆盖已有文件', ok, f'HTTP {r.status_code} overwritten={r.json().get("overwritten") if r.status_code==200 else "N/A"}')

# 6. 非法类型
r = client.post('/api/admin/data-files/upload', headers=H_ADMIN,
               files={'file': ('hack.txt', io.BytesIO(b'evil'), 'text/plain')},
               data={'overwrite':'false'})
check('非法类型拒绝', r.status_code == 400, f'HTTP {r.status_code}')

# 7. 路径穿越
r = client.post('/api/admin/data-files/upload', headers=H_ADMIN,
               files={'file': ('../escaped.xlsx', io.BytesIO(xlsx_bytes), 'application/vnd.openxmlformats')},
               data={'overwrite':'false'})
if r.status_code == 200:
    saved = r.json().get('name')
    safe = saved == 'escaped.xlsx'  # 应被降级为 basename
    check('路径穿越降级为 basename', safe, f'name={saved} (应=escaped.xlsx)')
else:
    check('路径穿越降级为 basename', r.status_code in (400, 200), f'HTTP {r.status_code}')

# 7b. 路径穿越 (Windows 风格)
r = client.post('/api/admin/data-files/upload', headers=H_ADMIN,
               files={'file': ('..\\win_escaped.xlsx', io.BytesIO(xlsx_bytes), 'application/vnd.openxmlformats')},
               data={'overwrite':'false'})
if r.status_code == 200:
    saved = r.json().get('name')
    safe = saved == 'win_escaped.xlsx'
    check('Win 风格路径穿越', safe, f'name={saved}')
else:
    check('Win 风格路径穿越', r.status_code in (400, 200), f'HTTP {r.status_code}')

# 8. list 验证
r = client.get('/api/admin/data-files', headers=H_ADMIN)
names = [f['name'] for f in r.json().get('files', [])]
check('list 含 fresh_test.xlsx', 'fresh_test.xlsx' in names, f'共 {len(names)} 个文件')
check('list 含 escaped.xlsx', 'escaped.xlsx' in names, '路径穿越已保存到 DATA_DIR 内部')
check('list 不含 ../escaped.xlsx', '../escaped.xlsx' not in names, '成功避免逃逸')

# 9. delete
r = client.delete('/api/admin/data-files/fresh_test.xlsx', headers=H_ADMIN)
check('删除文件', r.status_code == 200, f'HTTP {r.status_code}')

# 10. delete 不存在
r = client.delete('/api/admin/data-files/fresh_test.xlsx', headers=H_ADMIN)
check('删除不存在 → 404', r.status_code == 404, f'HTTP {r.status_code}')

# 11. 非管理员上传
r = client.post('/api/admin/data-files/upload', headers=H_USER,
               files={'file': ('x.xlsx', io.BytesIO(xlsx_bytes), 'application/vnd.openxmlformats')})
check('非管理员上传 → 403', r.status_code == 403, f'HTTP {r.status_code}')

# 12. 非管理员删除
r = client.delete('/api/admin/data-files/anything.xlsx', headers=H_USER)
check('非管理员删除 → 403', r.status_code == 403, f'HTTP {r.status_code}')

# 清理
import pathlib
for f in ['escaped.xlsx', 'win_escaped.xlsx', 'fresh_test.xlsx']:
    p = pathlib.Path('./data/files') / f
    if p.exists():
        p.unlink()

line('=' * 70)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
line(f'结果：{passed} / {total} 通过')
line('=' * 70)

if passed != total:
    line('\n失败项：')
    for name, ok, detail in results:
        if not ok:
            line(f'  ❌ {name}: {detail}')
    sys.exit(1)
else:
    line('🎉 全部通过')
