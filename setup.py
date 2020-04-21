from setuptools import setup

with open("kasa/version.py") as f:
    exec(f.read())

setup(
    name="python-kasa",
    version=__version__,  # type: ignore # noqa: F821
    description="Python API for TP-Link Kasa Smarthome products",
    url="https://github.com/python-kasa/python-kasa",
    author="",
    author_email="",
    license="GPLv3",
    packages=["kasa"],
    install_requires=["asyncclick"],
    python_requires=">=3.7",
    entry_points={"console_scripts": ["kasa=kasa.cli:cli"]},
    zip_safe=False,
)
