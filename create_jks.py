import sys
import os
import subprocess
import hashlib
import re
import datetime
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox
)

def generate_file_md5(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def create_jks(package_name, chinese_package_name, save_path, log_display):
    alias = "key0"
    dname = f"CN={package_name}, OU=dev, O=company, L=sh, ST=sh, C=CN"
    keystore = os.path.join(save_path, f"{package_name}.jks")
    storepass = keypass = "123456"

    # 根据中文包名创建文件夹
    target_folder = os.path.join(save_path, chinese_package_name)
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    # 更新保存路径为新创建的文件夹
    save_path = target_folder
    keystore = os.path.join(save_path, f"{package_name}.jks")

    keytool_cmd = [
        "keytool", "-genkeypair",
        "-alias", alias,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "36500",
        "-keystore", keystore,
        "-storepass", storepass,
        "-keypass", keypass,
        "-dname", dname,
        "-deststoretype", "JKS"
    ]

    try:
        subprocess.run(keytool_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 导出证书内容为 PEM 格式
        modulus_cmd = [
            "keytool", "-exportcert",
            "-alias", alias,
            "-keystore", keystore,
            "-storepass", storepass,
            "-rfc"
        ]
        result_mod = subprocess.run(modulus_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pem_data = result_mod.stdout

        # 确保 PEM 文件在临时目录生成
        tmp_cert_path = os.path.join(save_path, "tmp_cert.pem")
        with open(tmp_cert_path, "w") as f:
            f.write(pem_data)

        # 获取 SHA1 指纹
        cert_cmd = [
            "keytool", "-list", "-v",
            "-keystore", keystore,
            "-storepass", storepass
        ]
        result = subprocess.run(cert_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        cert_info = result.stdout
        sha1_match = re.search(r"SHA1:\s*([A-F0-9:]{59})", cert_info, re.IGNORECASE)
        sha1 = sha1_match.group(1) if sha1_match else "提取失败"

        # 获取证书的 MD5 指纹
        openssl_md5_cmd = [
            "openssl", "x509", "-in", tmp_cert_path, "-noout", "-fingerprint", "-md5"
        ]
        result_md5 = subprocess.run(openssl_md5_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        md5 = result_md5.stdout.split("=")[-1].strip() if result_md5.stdout else "提取失败"

        # 获取十进制 Modulus
        openssl_cmd = [
            "openssl", "x509", "-noout", "-modulus", "-in", tmp_cert_path
        ]
        result_modulus = subprocess.run(openssl_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        hex_modulus = result_modulus.stdout.strip().split('=')[-1]
        dec_modulus = str(int(hex_modulus, 16)) if hex_modulus else "提取失败"

        # 删除临时的 PEM 文件
        os.remove(tmp_cert_path)

        # 获取 JKS 文件的 MD5
        md5_from_jks = generate_file_md5(keystore)

        # 日志输出
        log_display.append(f"\n📌 证书 MD5 指纹: {md5}")
        log_display.append(f"📌 证书 SHA1 指纹: {sha1}")
        log_display.append(f"🔢 Modulus (十进制):\n{dec_modulus}")

        # 写入 info 文件
        info_file = os.path.join(save_path, f"{package_name}_jks_info.txt")
        info_content = f"""包名证书信息 - {package_name}
================================

📌 MD5 指纹:
{md5}

📌 SHA1 指纹:
{sha1}

🔢 Modulus (十进制):
{dec_modulus}

📅 生成时间: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        with open(info_file, "w", encoding="utf-8") as f:
            f.write(info_content)

    except subprocess.CalledProcessError as e:
        log_display.append(f"❌ 生成 JKS 失败: {e.stderr}")
        return

class JKSGeneratorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JKS 生成工具")
        self.resize(600, 500)
        layout = QVBoxLayout()

        layout.addWidget(QLabel("包名（用于生成证书别名）:"))
        self.package_input = QLineEdit()
        layout.addWidget(self.package_input)

        # 新增中文包名输入框
        layout.addWidget(QLabel("中文包名（用于生成文件夹）:"))
        self.chinese_package_input = QLineEdit()
        layout.addWidget(self.chinese_package_input)

        layout.addWidget(QLabel("保存路径:"))
        self.path_input = QLineEdit()
        layout.addWidget(self.path_input)

        self.browse_button = QPushButton("选择路径")
        self.browse_button.clicked.connect(self.browse_folder)
        layout.addWidget(self.browse_button)

        self.generate_button = QPushButton("生成 JKS")
        self.generate_button.clicked.connect(self.generate_jks)
        layout.addWidget(self.generate_button)

        layout.addWidget(QLabel("日志输出:"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)

        self.setLayout(layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存路径")
        if folder:
            self.path_input.setText(folder)

    def generate_jks(self):
        package_name = self.package_input.text().strip()
        chinese_package_name = self.chinese_package_input.text().strip()
        save_path = self.path_input.text().strip()

        if not package_name or not save_path or not chinese_package_name:
            QMessageBox.warning(self, "输入错误", "请填写包名、中文包名并选择保存路径！")
            return

        self.log_display.clear()
        self.log_display.append(f"🚀 开始生成 {package_name}.jks ...")
        create_jks(package_name, chinese_package_name, save_path, self.log_display)
        self.log_display.append("\n✅ JKS 生成完成！")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JKSGeneratorApp()
    window.show()
    sys.exit(app.exec_())
