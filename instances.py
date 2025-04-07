import os
import subprocess
import platform
import shutil
import sys
import time
import re
import threading
from tqdm import tqdm
import argparse


def get_gradle_command():
    return "gradlew.bat" if platform.system() == "Windows" else "./gradlew"


def run_command(command, cwd=None, check=True):
    process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if check and process.returncode != 0:
        print(f"❌ Error: {stderr.strip()}")
        sys.exit(1)

    return stdout.strip()


# 1. Gradle版本检测 & 自动 wrapper
def ensure_gradle_wrapper(project_dir):
    gradle_path = os.path.join(project_dir, 'gradlew')
    if not os.path.exists(gradle_path):
        print("🔧 Gradle Wrapper 不存在，正在自动生成...")
        run_command("gradle wrapper", cwd=project_dir)
    else:
        print("✅ Gradle Wrapper 已存在")

# 2. 动态获取所有flavor
def get_all_flavors(project_dir):
    print("🔍 正在读取 productFlavors...")
    gradle_file = os.path.join(project_dir, 'app', 'build.gradle')

    with open(gradle_file, 'r', encoding='utf-8') as f:
        content = f.read()

    matches = re.findall(r'productFlavors\s*\{([\s\S]*?)\}', content)
    if not matches:
        print("❌ 无法找到 productFlavors 配置")
        sys.exit(1)

    flavors = re.findall(r'(\w+)\s*\{', matches[0])
    print(f"🎯 检测到 Flavors: {flavors}")
    return flavors


# 清理build
def clean_build(project_dir):
    print("🧹 清理旧build")
    build_path = os.path.join(project_dir, 'app', 'build')
    if os.path.exists(build_path):
        shutil.rmtree(build_path)


def checkout_branch(branch_name, project_dir):
    if branch_name:
        print(f"🚀 切换分支 {branch_name}")
        run_command("git fetch --all", cwd=project_dir)
        run_command(f"git checkout {branch_name}", cwd=project_dir)
        run_command("git pull", cwd=project_dir)


# 3. APK校验
def validate_apk(apk_path):
    if not os.path.exists(apk_path):
        print(f"❌ APK 不存在: {apk_path}")
        return False

    size = os.path.getsize(apk_path) / 1024 / 1024
    print(f"📦 APK 大小: {size:.2f} MB")

    if size < 2:
        print("⚠️ APK 大小异常，可能构建失败")
        return False

    return True


MAX_RETRY = 3

def build_flavor_with_retry(flavor, project_dir, output_dir, progress_bar):
    for attempt in range(1, MAX_RETRY + 1):
        print(f"\n🔄 第{attempt}次尝试构建 {flavor} ...")

        gradle_cmd = get_gradle_command()
        cmd = f"{gradle_cmd} assemble{flavor.capitalize()}Release --rerun-tasks --parallel --daemon"

        run_command(cmd, cwd=project_dir)

        apk_dir = os.path.join(project_dir, 'app', 'build', 'outputs', 'apk', flavor, 'release')
        if not os.path.exists(apk_dir):
            print("❌ APK 路径不存在")
            continue

        for apk in os.listdir(apk_dir):
            if apk.endswith('.apk'):
                src = os.path.join(apk_dir, apk)
                dst = os.path.join(output_dir, apk)
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)

                if validate_apk(dst):
                    print(f"✅ 构建成功: {dst}")
                    progress_bar.update(1)
                    return
        print("⚠️ APK 构建失败，重试...")

    print(f"❌ 最多尝试{MAX_RETRY}次，{flavor} 构建失败")
    sys.exit(1)


def build_apk_parallel(flavors, project_dir, output_dir):
    progress_bar = tqdm(total=len(flavors), desc="构建进度")
    threads = []

    for flavor in flavors:
        t = threading.Thread(target=build_flavor_with_retry, args=(flavor, project_dir, output_dir, progress_bar))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    progress_bar.close()


# 7. 可视化入口
def interactive_mode():
    print("===== Android 极速打包器 =====")
    project_dir = input("请输入项目路径: ").strip()
    branch = input("请输入要切换的分支（留空不切换）: ").strip()
    output_dir = input("请输入APK输出目录: ").strip()

    ensure_gradle_wrapper(project_dir)
    checkout_branch(branch, project_dir)

    flavors = get_all_flavors(project_dir)
    print("\n可选渠道: ", flavors)
    selected = input("请输入要打包的flavor，多个用逗号（,）分隔，留空全部: ").strip()

    if not selected:
        selected_flavors = flavors
    else:
        selected_flavors = [f.strip() for f in selected.split(",") if f.strip() in flavors]

    clean_build(project_dir)

    os.makedirs(output_dir, exist_ok=True)
    start = time.time()
    build_apk_parallel(selected_flavors, project_dir, output_dir)
    print(f"\n🎉 所有 APK 构建完成! 总耗时 {time.time() - start:.2f} 秒")


if __name__ == "__main__":
    interactive_mode()
