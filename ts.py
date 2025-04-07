import os
import platform
import subprocess
import argparse
import sys
import time
import shutil
from tqdm import tqdm
from multiprocessing import Pool, Manager

MAX_RETRIES = 2


def get_gradle_command():
    return "gradlew.bat" if platform.system() == "Windows" else "./gradlew"


def run_command(command, cwd=None):
    process = subprocess.Popen(command, shell=True, cwd=cwd,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    stdout, stderr = process.communicate()

    if process.returncode != 0:
        raise RuntimeError(stderr.strip())

    return stdout.strip()


def clean_build(project_dir):
    build_path = os.path.join(project_dir, "app", "build")
    if os.path.exists(build_path):
        shutil.rmtree(build_path)


def handle_git_conflict(project_dir):
    status_output = run_command("git status --porcelain", cwd=project_dir)
    if "app/proguardMapping.txt" in status_output:
        run_command("git checkout -- app/proguardMapping.txt", cwd=project_dir)


def checkout_branch(branch_name, project_dir):
    if branch_name:
        handle_git_conflict(project_dir)
        run_command("git fetch --all", cwd=project_dir)
        run_command(f"git checkout {branch_name}", cwd=project_dir)
        run_command("git pull", cwd=project_dir)


def find_apk_path(project_dir, flavor):
    apk_dir = os.path.join(project_dir, "app", "build", "outputs", "apk", flavor, "release")
    if not os.path.exists(apk_dir):
        raise FileNotFoundError(f"{apk_dir} 不存在")

    apk_list = [f for f in os.listdir(apk_dir) if f.endswith(".apk")]
    if not apk_list:
        raise FileNotFoundError(f"{apk_dir} 无 APK 文件")

    return os.path.join(apk_dir, apk_list[0])


def build_flavor(flavor, project_dir, output_dir):
    gradle_cmd = get_gradle_command()
    build_cmd = f"{gradle_cmd} assemble{flavor.capitalize()}Release --build-cache --parallel --daemon --configuration-cache"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"\n🚀 构建 {flavor} (第 {attempt} 次)...")
            run_command(build_cmd, cwd=project_dir)
            apk_path = find_apk_path(project_dir, flavor)
            shutil.move(apk_path, os.path.join(output_dir, os.path.basename(apk_path)))
            print(f"✅ {flavor} 构建成功")
            return
        except Exception as e:
            print(f"⚠️ {flavor} 构建失败: {e}")
            if attempt < MAX_RETRIES:
                print(f"🔄 清理 {flavor} 并重试...")
                clean_build(project_dir)
            else:
                print(f"❌ {flavor} 构建失败，已达最大重试次数")
                raise e


def parallel_build(args):
    flavor, project_dir, output_dir, queue = args
    start = time.time()
    try:
        build_flavor(flavor, project_dir, output_dir)
        queue.put((flavor, True, time.time() - start))
    except:
        queue.put((flavor, False, time.time() - start))


def build_apks(flavors, project_dir, output_dir):
    with Manager() as manager:
        queue = manager.Queue()
        pool = Pool(processes=min(len(flavors), os.cpu_count() or 4))

        pool.map(parallel_build, [(f, project_dir, output_dir, queue) for f in flavors])
        pool.close()
        pool.join()

        results = []
        while not queue.empty():
            results.append(queue.get())

        for flavor, success, duration in results:
            status = "成功" if success else "失败"
            print(f"📦 {flavor} 构建{status} ⏱ {duration:.2f}s")

        if any(not success for _, success, _ in results):
            print("\n❌ 存在失败的渠道，请检查日志")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="🚀 极速多渠道打包脚本")
    parser.add_argument("--branch", help="Git 分支", default=None)
    parser.add_argument("--flavors", help="渠道列表(逗号分隔)", required=True)
    parser.add_argument("--project", help="Android 工程路径", required=True)
    parser.add_argument("--output", help="APK 输出路径", required=True)
    args = parser.parse_args()

    flavors = args.flavors.split(",")
    project_dir = os.path.abspath(args.project)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    checkout_branch(args.branch, project_dir)

    start_time = time.time()
    build_apks(flavors, project_dir, output_dir)
    print(f"\n🎉 所有渠道打包完成，总用时 ⏱ {time.time() - start_time:.2f}s")


if __name__ == "__main__":
    main()
