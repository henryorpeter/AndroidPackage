import os
import re


def get_gradle_version(project_dir):
    properties_path = os.path.join(project_dir, 'gradle', 'wrapper', 'gradle-wrapper.properties')
    with open(properties_path, 'r') as f:
        content = f.read()
    version = re.search(r'distributionUrl=.*gradle-(.*)-bin.zip', content)
    return version.group(1) if version else None


def get_product_flavors(project_dir):
    gradle_path = os.path.join(project_dir, 'app', 'build.gradle')
    with open(gradle_path, 'r', encoding='utf-8') as f:
        content = f.read()
    flavors = re.findall(r'productFlavors\s*{([^}]*)}', content, re.S)
    if not flavors:
        return []
    return re.findall(r'(\w+)\s*{', flavors[0])
