import os
import subprocess
import shutil
import sys
import time
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget, QPushButton, QFileDialog, QLineEdit, QTextEdit, QLabel, QHBoxLayout
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat, QFont
from datetime import datetime

def get_gradle_command():
    return "gradlew.bat" if os.name == "nt" else "./gradlew"

# 线程安全日志管理
class Logger:
    def __init__(self, log_signal):
        self.log_signal = log_signal

    def info(self, msg):
        self._output(msg, "black")

    def warn(self, msg):
        self._output(f"⚠️ {msg}", "orange")

    def error(self, msg):
        self._output(f"❌ {msg}", "red")

    def _output(self, msg, color):
        now = time.strftime("[%H:%M:%S] ")
        log_line = now + msg
        self.log_signal.emit((log_line, color))


def run_command(command, cwd, logger):
    process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='ignore')
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        logger.error(stderr.strip())
        raise Exception(stderr.strip())
    return stdout.strip()


def clean_build(project_dir, logger):
    build_path = os.path.join(project_dir, "app", "build")
    if os.path.exists(build_path):
        logger.info("🧹 清理旧构建...")
        shutil.rmtree(build_path)


def handle_git_conflict(project_dir, logger):
    status_output = run_command("git status --porcelain", cwd=project_dir, logger=logger)
    if "app/proguardMapping.txt" in status_output:
        run_command("git checkout -- app/proguardMapping.txt", cwd=project_dir, logger=logger)


def checkout_branch(branch_name, project_dir, logger):
    if branch_name:
        logger.info(f"🚀 切换分支: {branch_name}")
        handle_git_conflict(project_dir, logger)
        run_command("git fetch --all", cwd=project_dir, logger=logger)
        run_command(f"git checkout {branch_name}", cwd=project_dir, logger=logger)
        run_command("git pull", cwd=project_dir, logger=logger)


def build_flavor(flavor, project_dir, output_dir, logger):
    logger.info(f"🚀 开始构建 {flavor} ...")
    gradle_cmd = get_gradle_command()
    command = f"{gradle_cmd} assemble{flavor.capitalize()}Release --parallel --configuration-cache --build-cache --daemon --no-daemon --no-scan --no-watch-fs --offline"
    logger.info(f"执行命令: {command}")

    start_time = time.time()

    process = subprocess.Popen(command, shell=True, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='ignore')

    for line in process.stdout:
        logger.info(line.strip())

    for line in process.stderr:
        logger.error(line.strip())

    process.wait()
    duration = time.time() - start_time

    if process.returncode != 0:
        raise Exception("Gradle 构建失败")

    apk_path = os.path.join(project_dir, "app", "build", "outputs", "apk", flavor, "release")
    if os.path.exists(apk_path):
        for f in os.listdir(apk_path):
            if f.endswith(".apk"):
                src = os.path.join(apk_path, f)
                dst = os.path.join(output_dir, f)
                shutil.move(src, dst)
                logger.info(f"✅ APK 完成: {dst} (耗时 {duration:.2f}s)")
    else:
        logger.error(f"{apk_path} 不存在")


class BuildThread(QThread):
    log_signal = pyqtSignal(tuple)

    def __init__(self, project_dir, output_dir, flavors, branch_name):
        super().__init__()
        self.project_dir = project_dir
        self.output_dir = output_dir
        self.flavors = flavors
        self.branch_name = branch_name

    def run(self):
        logger = Logger(self.log_signal)
        try:
            clean_build(self.project_dir, logger)  # 可以选择不调用 clean_build 来进一步加速
            checkout_branch(self.branch_name, self.project_dir, logger)
            for flavor in self.flavors:
                build_flavor(flavor, self.project_dir, self.output_dir, logger)
            logger.info("🎉 所有渠道打包完成")
        except Exception as e:
            logger.error(str(e))


class PackagingToolUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Android 多渠道打包工具(V1.0.1)")
        self.setGeometry(100, 100, 700, 600)

        # 整体布局
        layout = QVBoxLayout()

        # 设置字体
        font = QFont("Arial", 10)
        self.setFont(font)

        # 项目路径输入框及按钮
        self.project_path_edit = QLineEdit()
        self.project_path_edit.setPlaceholderText("选择项目路径")
        btn1 = QPushButton("选择项目路径")
        btn1.clicked.connect(self.choose_project)

        # 输出路径输入框及按钮
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("选择输出路径")
        btn2 = QPushButton("选择输出路径")
        btn2.clicked.connect(self.choose_output)

        # 渠道名输入框
        self.flavors_edit = QLineEdit()
        self.flavors_edit.setPlaceholderText("输入渠道名, 多个逗号分隔")

        # Git 分支输入框
        self.branch_edit = QLineEdit()
        self.branch_edit.setPlaceholderText("输入Git分支 (留空则使用当前分支)")

        # 日志框
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)

        # 开始打包按钮
        btn3 = QPushButton("开始极速打包")
        btn3.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 5px; padding: 10px; font-weight: bold;")
        btn3.clicked.connect(self.start_build)

        # 布局管理
        layout.addWidget(QLabel("项目路径"))
        layout.addWidget(self.project_path_edit)
        layout.addWidget(btn1)
        layout.addWidget(QLabel("输出路径"))
        layout.addWidget(self.output_path_edit)
        layout.addWidget(btn2)
        layout.addWidget(QLabel("渠道名"))
        layout.addWidget(self.flavors_edit)
        layout.addWidget(QLabel("Git分支"))
        layout.addWidget(self.branch_edit)
        layout.addWidget(btn3)
        layout.addWidget(QLabel("构建日志"))
        layout.addWidget(self.log_edit)

        self.setLayout(layout)

    def choose_project(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目路径")
        if path:
            self.project_path_edit.setText(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出路径")
        if path:
            self.output_path_edit.setText(path)

    def start_build(self):
        project_dir = self.project_path_edit.text()
        output_dir = self.output_path_edit.text()
        flavors = [f.strip() for f in self.flavors_edit.text().split(",") if f.strip()]
        branch_name = self.branch_edit.text()

        if not os.path.exists(project_dir) or not os.path.exists(output_dir) or not flavors:
            self.append_log(("参数不完整！", "red"))
            return

        self.thread = BuildThread(project_dir, output_dir, flavors, branch_name)
        self.thread.log_signal.connect(self.append_log)
        self.thread.start()

    def append_log(self, log):
        text, color = log
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", fmt)
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = PackagingToolUI()
    win.show()
    sys.exit(app.exec_())
