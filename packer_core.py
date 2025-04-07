import os
import subprocess
import shutil
from tqdm import tqdm
from gradle_utils import get_gradle_version, get_product_flavors
from apk_checker import get_apk_info


def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(result.stderr)
        raise Exception("Command Error")
    return result.stdout


def build_apk(project_dir, output_dir, flavors, branch=None):
    gradle_version = get_gradle_version(project_dir)
    print(f"Gradle Version Detected: {gradle_version}")

    if branch:
        run_cmd(f"git checkout {branch}", cwd=project_dir)
        run_cmd("git pull", cwd=project_dir)

    run_cmd("./gradlew clean", cwd=project_dir)

    progress = tqdm(total=len(flavors))

    for flavor in flavors:
        print(f"Building {flavor}...")
        run_cmd(f"./gradlew assemble{flavor.capitalize()}Release --parallel --configuration-cache --daemon", cwd=project_dir)

        apk_dir = os.path.join(project_dir, 'app', 'build', 'outputs', 'apk', flavor, 'release')
        for apk in os.listdir(apk_dir):
            if apk.endswith(".apk"):
                src = os.path.join(apk_dir, apk)
                dst = os.path.join(output_dir, apk)
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)
                print("APK INFO:", get_apk_info(dst))
        progress.update(1)

    progress.close()
