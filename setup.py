from setuptools import setup
from setuptools.command.install import install
import os
import shutil
import sys

class PostInstallCommand(install):
    """Register with Claude CLI / Codex after installation."""
    def run(self):
        install.run(self)

        # Resolve the source directory.
        source_dir = os.path.dirname(os.path.abspath(__file__))

        # Claude CLI skill path.
        claude_skills_dir = os.path.expanduser("~/.claude/skills/solidworks-automation")

        # Codex skill path.
        codex_skills_dir = os.path.expanduser("~/.codex/skills/solidworks-automation")

        # Files and directories to copy.
        items_to_copy = ["scripts", "references", "mcp-server", "SKILL.md", "README.md", "README.tr.md", "localization", "requirements.txt"]

        for target_dir in [claude_skills_dir, codex_skills_dir]:
            try:
                os.makedirs(target_dir, exist_ok=True)
                for item in items_to_copy:
                    src = os.path.join(source_dir, item)
                    dst = os.path.join(target_dir, item)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    elif os.path.isfile(src):
                        shutil.copy2(src, dst)
                print(f"✓ Kuruldu / Installed: {target_dir}")
            except Exception as e:
                print(f"⚠ Atlandı / Skipped {target_dir}: {e}", file=sys.stderr)

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="solidworks-automation",
    version="2.0.0",
    author="wzyn20051216",
    description="Python automation toolkit for SolidWorks API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Luxeville-Group/solidworks-automation-skill",
    license="MIT",
    packages=["solidworks_automation"],
    package_dir={"solidworks_automation": "scripts"},
    cmdclass={"install": PostInstallCommand},
    install_requires=["pywin32>=305", "comtypes>=1.2.0"],
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
    ],
    keywords="solidworks automation cad api",
)
