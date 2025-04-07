import os
import hashlib
import subprocess


def md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_apk_info(apk_path):
    size = os.path.getsize(apk_path)
    apk_md5 = md5(apk_path)

    # 签名信息（只检测V1签名）
    result = subprocess.run(f'apksigner verify --verbose {apk_path}', shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    signed = "SIGNED" if "Verified" in result.stdout else "UNSIGNED"

    return {
        'path': apk_path,
        'size': size,
        'md5': apk_md5,
        'signed': signed
    }
