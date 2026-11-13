"""Build a portable V3 handoff ZIP and verify each entry against SHA256.json."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '3.1.6'
RELEASE_DATE = '20261113'
RELEASE = ROOT / 'releases' / f'surgerybox-v3-{VERSION}'


def main():
    metadata = json.loads((RELEASE / 'validation.json').read_text(encoding='utf-8'))
    binary = RELEASE / 'firmware.bin'
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == metadata['sha256'], 'Firmware hash mismatch'
    assert metadata['firmware'] == VERSION and metadata['protocol'] == 8
    assert f'firmware={VERSION},protocol=8' in (ROOT / 'firmware/v3/src/main.cpp').read_text(encoding='utf-8')
    paths = [
        ROOT / 'AGENTS.md',
        ROOT / 'firmware/v3/platformio.ini', ROOT / 'firmware/v3/README.md',
        *sorted((ROOT / 'firmware/v3/include').glob('*.h')),
        *sorted((ROOT / 'firmware/v3/src').glob('*.cpp')),
        *sorted((ROOT / 'host_sdk').glob('*.py')),
        *sorted((ROOT / 'host_sdk').glob('requirements*.txt')),
        ROOT / 'host_sdk/tests/test_client.py',
        ROOT / 'tools/StartHardwareTest.cmd', ROOT / 'tools/v3_test_client.py',
        ROOT / 'tools/test_v3_test_client.py', Path(__file__).resolve(),
        ROOT / 'docs/AI-HANDOFF.md', ROOT / 'docs/v3-hardware-api.md',
        ROOT / 'docs/v3-test-console.md', ROOT / 'docs/v3-hardware-validation.md',
        ROOT / 'docs/v3-release-notes.md',
        *sorted(p for p in RELEASE.iterdir() if p.is_file()),
    ]
    entries = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in paths}
    entries['README.md'] = (
        f'# SurgeryBox V3 {VERSION} / protocol=8\n\n'
        '先读[交接说明](docs/AI-HANDOFF.md)和[硬件接口](docs/v3-hardware-api.md)。\n\n'
        '安装：`python -m pip install -r host_sdk/requirements-gui.txt`\n\n'
        '测试端：`python tools/v3_test_client.py --port COM4`；Windows可双击`tools/StartHardwareTest.cmd`。\n\n'
        '上电自动设零点，也可手动设置实际回卷零点。D8 回卷，D7 释放；舵机目标 180°/90°/30°。\n\n'
        f'固件源码在 firmware/v3。已烧录镜像和现场证据在 releases/surgerybox-v3-{VERSION}。\n'
        '包内SHA256.json逐文件列出校验值；剩余问题见交接说明。\n'
    ).encode('utf-8')
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}
    entries['SHA256.json'] = json.dumps(manifest, indent=2).encode('utf-8')
    output = ROOT / 'releases' / f'surgerybox-v3-{VERSION}-{RELEASE_DATE}.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as package:
        for name, data in entries.items():
            package.writestr(name, data)
    with zipfile.ZipFile(output) as package:
        assert package.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(package.read(name)).hexdigest() == digest, name
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (ROOT / 'releases' / f'SHA256SUMS-v{VERSION}.txt').write_text(
        f'{digest}  {output.name}\n{metadata["sha256"]}  firmware.bin\n', encoding='utf-8')
    print(json.dumps({'file': str(output), 'files': len(entries), 'bytes': output.stat().st_size,
                      'sha256': digest, 'all_entries_verified': True}))


if __name__ == '__main__':
    main()
