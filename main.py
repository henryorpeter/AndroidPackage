import os
import platform
import subprocess
import threading
import sys
import time
import shutil
from tqdm import tqdm  # 进度条库
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget, QPushButton, QFileDialog, QLineEdit, QTextEdit
from PyQt5.QtCore import QThread, pyqtSignal


# 获取 Gradle 命令
def get_gradle_command():
    return "gradlew.bat" if platform.system() == "Windows" else "./gradlew"


# 运行 shell 命令
def run_command(command, cwd=None):
    process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(f"❌ 发生错误: {stderr.strip()}")
        sys.exit(1)

    return stdout.strip()


# 清理 Gradle 缓存，防止打包失败
def clean_build(project_dir):
    print("\n🧹 清理旧的构建文件...")
    build_path = os.path.join(project_dir, "app", "build")
    if os.path.exists(build_path):
        shutil.rmtree(build_path)


# 检查是否有未提交的更改，并处理
def handle_git_conflict(project_dir):
    print("\n🔍 检查是否有未提交的更改...")
    status_output = run_command("git status --porcelain", cwd=project_dir)

    if "app/proguardMapping.txt" in status_output:
        print("\n⚠️ 检测到 app/proguardMapping.txt 有未提交的更改！")
        print("\n🧹 丢弃本地修改...")
        run_command("git checkout -- app/proguardMapping.txt", cwd=project_dir)

    # 检查是否有未提交的更改，如果有，则执行 git stash
    if status_output:
        print("\n🧳 存储未提交的更改...")
        run_command("git stash", cwd=project_dir)


# 切换 Git 分支，自动处理未提交的更改
def checkout_branch(branch_name, project_dir):
    if branch_name:
        print(f"\n🚀 切换到分支 {branch_name}...")
        handle_git_conflict(project_dir)
        run_command("git fetch --all", cwd=project_dir)
        run_command(f"git checkout {branch_name}", cwd=project_dir)
        run_command("git pull", cwd=project_dir)

        # 恢复之前存储的更改
        status_output = run_command("git status --porcelain", cwd=project_dir)
        if status_output:
            print("\n🔄 恢复存储的更改...")
            run_command("git stash pop", cwd=project_dir)


# 构建单个渠道
def build_flavor(flavor, project_dir, output_dir, progress_bar, log_signal):
    print(f"\n🚀 开始构建 {flavor} 版本...")

    gradle_cmd = get_gradle_command()
    build_command = f"{gradle_cmd} assemble{flavor.capitalize()}Release --rerun-tasks --parallel --configuration-cache --daemon"

    log_signal.emit(f"🛠️ 执行命令: {build_command}")

    start_time = time.time()

    process = subprocess.Popen(build_command, shell=True, cwd=project_dir,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    stdout_lines = []
    stderr_lines = []

    # 读取 Gradle 输出并实时打印
    for line in process.stdout:
        log_signal.emit(line.strip())
        stdout_lines.append(line.strip())

    for line in process.stderr:
        log_signal.emit("🚨 Gradle 错误:" + line.strip())
        stderr_lines.append(line.strip())

    process.wait()
    elapsed_time = time.time() - start_time

    if process.returncode != 0:
        log_signal.emit("\n❌ Gradle 构建失败，完整错误如下:")
        log_signal.emit("\n".join(stderr_lines))
        sys.exit(1)

    # 复制 APK
    apk_path = os.path.join(project_dir, "app", "build", "outputs", "apk", flavor, "release")
    if os.path.exists(apk_path):
        for file in os.listdir(apk_path):
            if file.endswith(".apk"):
                src = os.path.join(apk_path, file)
                dst = os.path.join(output_dir, file)

                # **解决 WinError 183（目标文件已存在，无法覆盖）**
                if os.path.exists(dst):
                    log_signal.emit(f"\n⚠️ 目标文件已存在，删除旧文件: {dst}")
                    os.remove(dst)

                shutil.move(src, dst)  # 使用 shutil.move 避免 WinError 183
                log_signal.emit(f"\n✅ APK 生成: {dst} (⏱ {elapsed_time:.2f} 秒)")

                progress_bar.update(1)
    else:
        log_signal.emit(f"\n❌ 错误: {apk_path} 不存在，打包失败？")
        sys.exit(1)


# 并行构建所有渠道
def build_apk_parallel(flavors, project_dir, output_dir, log_signal):
    progress_bar = tqdm(total=len(flavors), desc="构建进度",
                        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} {elapsed} < {remaining}")

    threads = []

    for flavor in flavors:
        thread = threading.Thread(target=build_flavor, args=(flavor, project_dir, output_dir, progress_bar, log_signal))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    progress_bar.close()


# PyQt5 界面
class PackagingToolUI(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Android 多渠道打包工具")
        self.setGeometry(100, 100, 600, 400)

        layout = QVBoxLayout()

        self.project_path = QLineEdit(self)
        self.project_path.setPlaceholderText("选择 Android 项目目录")
        layout.addWidget(self.project_path)

        self.output_path = QLineEdit(self)
        self.output_path.setPlaceholderText("选择 APK 输出目录")
        layout.addWidget(self.output_path)

        self.flavors_input = QLineEdit(self)
        self.flavors_input.setPlaceholderText("输入渠道名称，逗号分隔")
        layout.addWidget(self.flavors_input)

        self.branch_input = QLineEdit(self)
        self.branch_input.setPlaceholderText("输入 Git 分支名称")
        layout.addWidget(self.branch_input)

        self.select_project_button = QPushButton("选择项目目录", self)
        self.select_project_button.clicked.connect(self.select_project_directory)
        layout.addWidget(self.select_project_button)

        self.select_output_button = QPushButton("选择输出目录", self)
        self.select_output_button.clicked.connect(self.select_output_directory)
        layout.addWidget(self.select_output_button)

        self.start_button = QPushButton("开始打包", self)
        self.start_button.clicked.connect(self.start_build)
        layout.addWidget(self.start_button)

        # 日志输出窗口
        self.log_output = QTextEdit(self)
        self.log_output.setPlaceholderText("显示日志...")
        self.log_output.setReadOnly(True)  # 设置为只读
        layout.addWidget(self.log_output)

        self.setLayout(layout)

        self.log_signal.connect(self.update_log)

    def select_project_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择项目目录")
        if directory:
            self.project_path.setText(directory)

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.output_path.setText(directory)

    def start_build(self):
        project_dir = self.project_path.text()
        output_dir = self.output_path.text()
        flavors = self.flavors_input.text().split(',')
        branch_name = self.branch_input.text()

        # 使用 QThread 处理耗时任务
        self.build_thread = BuildThread(branch_name, project_dir, output_dir, flavors, self.log_signal)
        self.build_thread.start()

    def update_log(self, log_text):
        self.log_output.append(log_text)


class BuildThread(QThread):
    def __init__(self, branch_name, project_dir, output_dir, flavors, log_signal):
        super().__init__()
        self.branch_name = branch_name
        self.project_dir = project_dir
        self.output_dir = output_dir
        self.flavors = flavors
        self.log_signal = log_signal

    def run(self):
        checkout_branch(self.branch_name, self.project_dir)
        clean_build(self.project_dir)
        build_apk_parallel(self.flavors, self.project_dir, self.output_dir, self.log_signal)


# 主函数
def main():
    app = QApplication(sys.argv)
    ui = PackagingToolUI()
    ui.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
