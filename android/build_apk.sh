#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="${ANDROID_HOME:-/opt/android-sdk}"
BUILD_TOOLS="${SDK_ROOT}/build-tools/35.0.0"
ANDROID_JAR="${SDK_ROOT}/platforms/android-35/android.jar"

SRC_DIR="${SCRIPT_DIR}/app/src/main"
BUILD_DIR="${SCRIPT_DIR}/build"
KEYSTORE="${SCRIPT_DIR}/dalalink-release.keystore"
OUT_APK="${SCRIPT_DIR}/DalaLink-Luanda-v1.0.apk"

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/compiled_res" "${BUILD_DIR}/gen" "${BUILD_DIR}/obj" "${BUILD_DIR}/dex"

echo "[1/6] Generating DalaLink Android launcher icons..."
python3 - <<'PY' "${SRC_DIR}/res"
import os, struct, zlib, sys

res_dir = sys.argv[1]

def write_png(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Draw crisp rounded emerald square with bold white navigation chevron
    rows = []
    cx = cy = (size - 1) / 2.0
    r_corner = size * 0.22
    for y in range(size):
        row = bytearray([0])  # filter byte 0
        for x in range(size):
            # Rounded square mask
            dx = max(0.0, abs(x - cx) - (size / 2.0 - r_corner))
            dy = max(0.0, abs(y - cy) - (size / 2.0 - r_corner))
            in_bg = (dx * dx + dy * dy) <= (r_corner * r_corner)

            # Navigation pointer / stylized "D" arrow in white
            nx = (x - cx) / (size * 0.36)
            ny = (y - cy) / (size * 0.36)
            # Upward mobility arrow polygon
            in_arrow = (
                ny >= -0.95 and ny <= 0.85
                and abs(nx) <= (ny + 0.95) * 0.52
                and not (ny > 0.32 and abs(nx) < (ny - 0.32) * 1.15)
            )
            # Amber accent dot near base
            in_dot = (nx * nx + (ny - 0.62) ** 2) <= 0.14 ** 2

            if not in_bg:
                row.extend((0, 0, 0, 0))
            elif in_dot:
                row.extend((245, 158, 11, 255))  # Amber
            elif in_arrow:
                row.extend((255, 255, 255, 255))  # Crisp white
            else:
                # Subtle emerald vertical gradient
                t = y / max(1, size - 1)
                row.extend((int(13 * (1 - t) + 9 * t), int(124 * (1 - t) + 91 * t), int(95 * (1 - t) + 69 * t), 255))
        rows.append(bytes(row))

    raw = b"".join(rows)
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)

for density, px in [("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)]:
    write_png(os.path.join(res_dir, f"mipmap-{density}", "ic_launcher.png"), px)
PY

echo "[2/6] Compiling Android resources with aapt2..."
"${BUILD_TOOLS}/aapt2" compile --dir "${SRC_DIR}/res" -o "${BUILD_DIR}/compiled_res/resources.zip"
"${BUILD_TOOLS}/aapt2" link \
  -I "${ANDROID_JAR}" \
  --manifest "${SRC_DIR}/AndroidManifest.xml" \
  -A "${SRC_DIR}/assets" \
  --java "${BUILD_DIR}/gen" \
  -o "${BUILD_DIR}/unsigned.apk" \
  "${BUILD_DIR}/compiled_res/resources.zip"

echo "[3/6] Compiling Java sources..."
javac --release 11 \
  -classpath "${ANDROID_JAR}" \
  -d "${BUILD_DIR}/obj" \
  "${SRC_DIR}/java/com/dalalink/luanda/MainActivity.java" \
  "${BUILD_DIR}/gen/com/dalalink/luanda/R.java"

echo "[4/6] Translating bytecode to Dalvik DEX with d8..."
"${BUILD_TOOLS}/d8" \
  --min-api 24 \
  --lib "${ANDROID_JAR}" \
  --output "${BUILD_DIR}/dex" \
  "${BUILD_DIR}/obj/com/dalalink/luanda/"*.class

echo "[5/6] Packaging DEX and aligning APK..."
(cd "${BUILD_DIR}/dex" && zip -q -u "${BUILD_DIR}/unsigned.apk" classes.dex)
"${BUILD_TOOLS}/zipalign" -f -p 4 "${BUILD_DIR}/unsigned.apk" "${BUILD_DIR}/aligned.apk"

echo "[6/6] Signing APK (v1/v2/v3) with apksigner..."
if [ ! -f "${KEYSTORE}" ]; then
  keytool -genkeypair -v \
    -keystore "${KEYSTORE}" \
    -storepass dalalink2026 \
    -keypass dalalink2026 \
    -alias dalalink \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=DalaLink Luanda, OU=Mobilidade, O=DalaLink, L=Luanda, ST=Luanda, C=AO"
fi

"${BUILD_TOOLS}/apksigner" sign \
  --ks "${KEYSTORE}" \
  --ks-pass pass:dalalink2026 \
  --key-pass pass:dalalink2026 \
  --ks-key-alias dalalink \
  --out "${OUT_APK}" \
  "${BUILD_DIR}/aligned.apk"

"${BUILD_TOOLS}/apksigner" verify --verbose "${OUT_APK}"
ls -lh "${OUT_APK}"
echo "SUCCESS: APK built at ${OUT_APK}"
