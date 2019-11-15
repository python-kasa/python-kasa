from setuptools import setup

with open("pyHS100/version.py") as f:
    exec(f.read())

setup(
    name="pyHS100",
    version=__version__,  # type: ignore # noqa: F821
    description="Python interface for TPLink KASA-enabled smart home devices",
    url="https://github.com/GadgetReactor/pyHS100",
    author="Sean Seah (GadgetReactor)",
    author_email="sean@gadgetreactor.com",
    license="GPLv3",
    packages=["pyHS100"],
    install_requires=["click", "deprecation"],
    python_requires=">=3.6",
    entry_points={"console_scripts": ["pyhs100=pyHS100.cli:cli"]},
    zip_safe=False,
)
