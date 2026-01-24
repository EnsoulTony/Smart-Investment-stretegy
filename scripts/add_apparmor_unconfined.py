#!/usr/bin/env python3
"""把 "apparmor=unconfined" 加到 docker-compose.yml 每個 service 的 security_opt。

用法：
  python3 scripts/add_apparmor_unconfined.py [path/to/docker-compose.yml]

此腳本會先備份原檔成 <file>.bak，再寫回修改後的檔案。
注意：會使用 PyYAML，預設系統應已安裝 Python 3；若沒安裝 PyYAML，請先 `pip install pyyaml`。
"""
import sys
from pathlib import Path
import yaml


def main():
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('docker-compose.yml')
    if not p.exists():
        print('file not found:', p)
        return 2
    bak = p.with_suffix(p.suffix + '.bak')
    bak.write_bytes(p.read_bytes())
    data = yaml.safe_load(p.read_text()) or {}
    services = data.get('services')
    if not services:
        print('no services found in', p)
        return 1
    for name, svc in services.items():
        if svc is None:
            svc = {}
        sopt = svc.get('security_opt')
        if sopt is None:
            svc['security_opt'] = ['apparmor=unconfined']
        else:
            # ensure list
            if not isinstance(sopt, list):
                svc['security_opt'] = [sopt]
                sopt = svc['security_opt']
            # 移除舊格式並添加新格式
            if 'apparmor:unconfined' in sopt:
                sopt.remove('apparmor:unconfined')
            if 'apparmor=unconfined' not in sopt:
                sopt.append('apparmor=unconfined')
        services[name] = svc
    data['services'] = services
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    print('updated', p, 'backup at', bak)
    return 0


if __name__ == '__main__':
    sys.exit(main())
