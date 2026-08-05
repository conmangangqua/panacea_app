#!/usr/bin/env python3
"""Localize icon app của hub — bản CHẠY TRONG CI (GitHub Actions của mỗi hub repo).

Vấn đề gốc: workflow `update-apps-json.yml` build lại apps.json from scratch mỗi lần có
release/cron, gán `icon` = URL GitHub release (~900KB/icon). Trước đây có bước localize thủ
công (localize_hub_icons.py chạy tay) nhưng lần regen kế tiếp XOÁ SỔ kết quả → 11/11 hub
quay về hotlink, site nạp ~900KB × N app (incident Sếp report 2026-07-27: hub bbl 36 app).

Script này chạy NGAY SAU bước build apps.json trong CI nên kết quả không bao giờ bị đè.

Khác biệt cốt tử so với bản chạy tay: KHÔNG skip mù theo "file đã tồn tại".
Ta lưu manifest `icons/_sources.json` = {app_id: {"sha": <sha256 icon nguồn>, "src": <url>}}.
- sha nguồn khớp manifest + file webp còn đó  → tái dùng, chỉ rewrite path (0 byte tải thêm).
- sha khác (Sếp đổi logo) hoặc thiếu file/manifest → tải + regen webp.
Nhờ vậy đổi logo là icon hub tự đổi theo, không cần ai nhớ chạy tay.

Fail-open: app nào tải/encode lỗi thì GIỮ NGUYÊN URL http của app đó — hub vẫn hiện icon
(chậm) thay vì vỡ ảnh, và không chặn các app còn lại.

Dùng: python3 scripts/localize_icons.py [hub_dir] [--size 192] [--quality 80]
Yêu cầu: `cwebp` (apt-get install -y webp).
"""
import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

MANIFEST_NAME = "_sources.json"


def log(m):
    print(f"[localize-icons] {m}", flush=True)


def download(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "hub-localize-icons"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hub_dir", nargs="?", default=".")
    ap.add_argument("--size", type=int, default=192)
    ap.add_argument("--quality", type=int, default=80)
    args = ap.parse_args()

    hub = Path(args.hub_dir).resolve()
    apps_json = hub / "apps.json"
    if not apps_json.exists():
        log(f"không thấy {apps_json} — bỏ qua")
        return 0

    data = load_json(apps_json, None)
    if data is None:
        log("apps.json không parse được — bỏ qua (không phá file)")
        return 0
    apps = data if isinstance(data, list) else data.get("apps", [])

    icons_dir = hub / "icons"
    icons_dir.mkdir(exist_ok=True)
    manifest_path = icons_dir / MANIFEST_NAME
    manifest = load_json(manifest_path, {})

    reused = regen = kept = 0
    failed = []

    for app in apps:
        if not isinstance(app, dict):
            continue
        aid = app.get("id")
        icon = app.get("icon") or ""
        if not aid:
            continue

        rel = f"icons/{aid}.webp"
        out = hub / rel
        entry = manifest.get(aid) or {}

        # Nguồn để so hash: URL trong apps.json, hoặc URL đã ghi nhớ ở manifest
        # (trường hợp apps.json đang trỏ sẵn path local).
        src = icon if icon.startswith("http") else entry.get("src") or ""
        if not src:
            # Không có nguồn: giữ nguyên field icon, không bịa.
            kept += 1
            continue

        try:
            raw = download(src)
        except Exception as e:
            failed.append((aid, f"tải nguồn lỗi: {str(e)[:70]}"))
            continue

        sha = hashlib.sha256(raw).hexdigest()
        if entry.get("sha") == sha and out.exists():
            app["icon"] = rel
            reused += 1
            continue

        tmp = Path("/tmp") / f"_icon_{aid}.src"
        try:
            tmp.write_bytes(raw)
            r = subprocess.run(
                ["cwebp", "-quiet", "-resize", str(args.size), "0",
                 "-q", str(args.quality), str(tmp), "-o", str(out)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0 or not out.exists():
                failed.append((aid, (r.stderr or "cwebp fail")[:70]))
                continue
            app["icon"] = rel
            manifest[aid] = {"sha": sha, "src": src}
            regen += 1
            log(f"regen {aid}: {len(raw)//1024}KB → {out.stat().st_size//1024}KB")
        except Exception as e:
            failed.append((aid, str(e)[:70]))
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass

    apps_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    log(f"xong: {regen} regen, {reused} tái dùng, {kept} giữ URL, {len(failed)} lỗi")
    for aid, why in failed:
        log(f"  ! {aid}: {why} (giữ nguyên URL http)")
    # Fail-open: lỗi lẻ không được làm đỏ pipeline hub.
    return 0


if __name__ == "__main__":
    sys.exit(main())
