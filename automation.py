import os
import platform
import subprocess
import argparse
import threading
import sys
import time
import shutil
from tqdm import tqdm  # 进度条库

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

# 处理 Git 冲突
def handle_git_conflict(project_dir):
    print("\n🔍 检查是否有未提交的更改...")
    status_output = run_command("git status --porcelain", cwd=project_dir)

    if "app/proguardMapping.txt" in status_output:
        print("\n⚠️ 检测到 app/proguardMapping.txt 有未提交的更改！")
        print("\n🧹 丢弃本地修改...")
        run_command("git checkout -- app/proguardMapping.txt", cwd=project_dir)

# 切换 Git 分支
def checkout_branch(branch_name, project_dir):
    if branch_name:
        print(f"\n🚀 切换到分支 {branch_name}...")
        handle_git_conflict(project_dir)
        run_command("git fetch --all", cwd=project_dir)
        run_command(f"git checkout {branch_name}", cwd=project_dir)
        run_command("git pull", cwd=project_dir)

# 构建单个渠道
def build_flavor(flavor, project_dir, output_dir, progress_bar):
    print(f"\n🚀 开始构建 {flavor} 版本...")

    gradle_cmd = get_gradle_command()
    build_command = f"{gradle_cmd} assemble{flavor.capitalize()}Release --rerun-tasks --parallel --configuration-cache --daemon"

    print(f"🛠️ 执行命令: {build_command}")

    start_time = time.time()

    process = subprocess.Popen(build_command, shell=True, cwd=project_dir,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    stdout_lines = []
    stderr_lines = []

    # 读取 Gradle 输出并实时打印
    for line in process.stdout:
        print(line.strip())
        stdout_lines.append(line.strip())

    for line in process.stderr:
        print("🚨 Gradle 错误:", line.strip())
        stderr_lines.append(line.strip())

    process.wait()
    elapsed_time = time.time() - start_time

    if process.returncode != 0:
        print("\n❌ Gradle 构建失败，完整错误如下:")
        print("\n".join(stderr_lines))
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
                    print(f"\n⚠️ 目标文件已存在，删除旧文件: {dst}")
                    os.remove(dst)

                shutil.move(src, dst)  # 使用 shutil.move 避免 WinError 183
                print(f"\n✅ APK 生成: {dst} (⏱ {elapsed_time:.2f} 秒)")
                progress_bar.update(1)
    else:
        print(f"\n❌ 错误: {apk_path} 不存在，打包失败？")
        sys.exit(1)

# 构建单个渠道，支持自动重试
MAX_RETRIES = 3
def build_flavor_with_retry(flavor, project_dir, output_dir, progress_bar):
    for attempt in range(MAX_RETRIES):
        print(f"\n🔄 第 {attempt + 1} 次尝试构建 {flavor}...")
        build_flavor(flavor, project_dir, output_dir, progress_bar)

        apk_path = os.path.join(project_dir, "app", "build", "outputs", "apk", flavor, "release")
        if os.path.exists(apk_path):
            print(f"✅ {flavor} 构建成功！")
            return

        print(f"\n⚠️ {flavor} 构建失败，重试中...")

    print(f"\n❌ {flavor} 仍然构建失败，已达到最大重试次数。")
    sys.exit(1)

# 并行构建所有渠道
def build_apk_parallel(flavors, project_dir, output_dir):
    progress_bar = tqdm(total=len(flavors), desc="构建进度",
                        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} {elapsed} < {remaining}")

    threads = []

    for flavor in flavors:
        thread = threading.Thread(target=build_flavor_with_retry, args=(flavor, project_dir, output_dir, progress_bar))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    progress_bar.close()

# 主函数
def main():
    parser = argparse.ArgumentParser(description="🚀 Android 极速打包脚本（带进度 + 统计用时）")
    parser.add_argument("--branch", help="Git 分支名称", default=None)
    parser.add_argument("--flavors", help="产品渠道列表, 逗号分隔", required=True)
    parser.add_argument("--project", help="Android 工程目录", required=True)
    parser.add_argument("--output", help="APK 输出目录", required=True)
    args = parser.parse_args()

    flavors = args.flavors.split(",")
    project_dir = os.path.abspath(args.project)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    checkout_branch(args.branch, project_dir)
    clean_build(project_dir)

    start_time = time.time()
    build_apk_parallel(flavors, project_dir, output_dir)
    end_time = time.time()

    total_time = end_time - start_time
    print(f"\n🎉 **所有 APK 构建完成！总用时: ⏱ {total_time:.2f} 秒**")

if __name__ == "__main__":
    main()
