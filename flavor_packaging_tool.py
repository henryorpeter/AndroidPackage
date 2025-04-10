import os
import shutil
import subprocess
import sys
import time
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget, QPushButton, QFileDialog, QLineEdit, QTextEdit, QLabel, \
    QCheckBox, QGridLayout
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor, QTextCharFormat, QFont, QTextCursor
import re

def get_gradle_command():
    return "gradlew.bat" if os.name == "nt" else "./gradlew"

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
    try:
        process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', errors='ignore')
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(stderr.strip())
            raise Exception(stderr.strip())
        return stdout.strip()
    except Exception as e:
        logger.error(f"命令执行失败: {e}")
        raise e

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

    try:
        process = subprocess.Popen(command, shell=True, cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', errors='ignore')

        for line in process.stdout:
            logger.info(line.strip())

        for line in process.stderr:
            logger.error(line.strip())

        process.wait()
    except Exception as e:
        logger.error(f"构建失败: {e}")
        raise e

    duration = time.time() - start_time

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

def find_flavors(project_dir):
    """
    万能解析Android项目的渠道配置
    支持以下写法：
    1. 直接定义: flavorName { ... }
    2. 动态创建: create("flavorName") { ... }
    3. 带引号定义: 'flavor-name' { ... }
    4. 多维度配置: missingDimensionStrategy 'dimension', 'flavor'
    5. 任意缩进和换行格式
    """
    gradle_file = os.path.join(project_dir, 'app', 'build.gradle')
    if not os.path.exists(gradle_file):
        return []

    with open(gradle_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 预处理：移除注释和字符串内容（保留结构）
    content = re.sub(r'//.*', '', content)  # 移除单行注释
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)  # 移除块注释
    content = re.sub(r'"(?:\\"|[^"])*"', '""', content)  # 替换字符串内容为空白
    content = re.sub(r"'(?:\\'|[^'])*'", "''", content)  # 替换字符串内容为空白

    flavors = set()  # 使用集合自动去重

    # 匹配所有可能的渠道定义模式
    patterns = [
        # 标准定义: flavorName { ... }
        r'(?:^|\s)([\w-]+)\s*\{',
        # 动态创建: create("flavorName") 或 create('flavorName')
        r'create\(\s*["\']?([\w-]+)["\']?\s*\)',
        # 带引号定义: 'flavor-name' { ... }
        r'["\']([\w-]+)["\']\s*\{',
        # 维度策略中的渠道引用（辅助识别）
        r"missingDimensionStrategy\s+.+,\s*['\"]([\w-]+)['\"]"
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            group = match.group(1) if match.lastindex == 1 else match.group(2)
            if group and len(group) > 1:  # 过滤单个字符的误匹配
                flavors.add(group)

    return sorted(flavors) if flavors else []

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
            clean_build(self.project_dir, logger)
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
        self.selected_flavors = []

        # 主布局
        layout = QVBoxLayout()

        # 项目路径
        self.project_path_edit = QLineEdit()
        self.project_path_edit.setPlaceholderText("选择项目路径")
        btn_project = QPushButton("选择项目路径")
        btn_project.clicked.connect(self.choose_project)

        # 输出路径
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("选择输出路径")
        btn_output = QPushButton("选择输出路径")
        btn_output.clicked.connect(self.choose_output)

        # 渠道选择容器
        self.flavor_container = QWidget()
        self.flavor_layout = QGridLayout(self.flavor_container)
        self.flavor_layout.addWidget(QLabel("选择渠道："), 0, 0, 1, 5)

        # Git分支
        self.branch_edit = QLineEdit()
        self.branch_edit.setPlaceholderText("输入Git分支 (留空则使用当前分支)")

        # 日志框
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)

        # 打包按钮
        btn_build = QPushButton("开始极速打包")
        btn_build.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        btn_build.clicked.connect(self.start_build)

        # 组装界面
        layout.addWidget(QLabel("项目路径"))
        layout.addWidget(self.project_path_edit)
        layout.addWidget(btn_project)
        layout.addWidget(QLabel("输出路径"))
        layout.addWidget(self.output_path_edit)
        layout.addWidget(btn_output)
        layout.addWidget(self.flavor_container)
        layout.addWidget(QLabel("Git分支"))
        layout.addWidget(self.branch_edit)
        layout.addWidget(btn_build)
        layout.addWidget(QLabel("构建日志"))
        layout.addWidget(self.log_edit)

        self.setLayout(layout)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出路径")
        if path:
            self.output_path_edit.setText(path)

    def choose_project(self):
        try:
            path = QFileDialog.getExistingDirectory(self, "选择项目路径")
            if not path:
                return

            self.project_path_edit.setText(path)
            flavors = find_flavors(path)

            # 清空旧复选框
            for child in self.flavor_container.findChildren(QCheckBox):
                child.deleteLater()

            # 添加新复选框
            if flavors:
                for i, flavor in enumerate(flavors):
                    cb = QCheckBox(flavor, self.flavor_container)
                    cb.toggled.connect(self.update_flavors)
                    row = (i // 5) + 1  # 从第1行开始
                    col = i % 5
                    self.flavor_layout.addWidget(cb, row, col)
            else:
                cb = QCheckBox("default", self.flavor_container)
                self.flavor_layout.addWidget(cb, 1, 0)

            self.update_flavors()

        except Exception as e:
            self.append_log(("错误: " + str(e), "red"))

    def update_flavors(self):
        self.selected_flavors = [
            cb.text() for cb in self.flavor_container.findChildren(QCheckBox)
            if cb.isChecked()
        ]
        print("当前选中的渠道:", self.selected_flavors)

    def start_build(self):
        project_dir = self.project_path_edit.text()
        output_dir = self.output_path_edit.text()

        if not os.path.exists(project_dir):
            self.append_log(("错误: 项目路径无效", "red"))
            return
        if not os.path.exists(output_dir):
            self.append_log(("错误: 输出路径无效", "red"))
            return
        if not self.selected_flavors:
            self.append_log(("错误: 请至少选择一个渠道", "red"))
            return

        self.build_thread = BuildThread(
            project_dir,
            output_dir,
            self.selected_flavors,
            self.branch_edit.text()
        )
        self.build_thread.log_signal.connect(self.append_log)
        self.build_thread.start()

    def append_log(self, log_data):
        log_msg, color = log_data
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(log_msg + '\n')
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PackagingToolUI()
    window.show()
    sys.exit(app.exec_())