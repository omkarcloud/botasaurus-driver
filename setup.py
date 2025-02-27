from setuptools import setup, find_packages

def get_description():
    try:
        with open("README.md", encoding="utf-8") as readme_file:
            long_description = readme_file.read()
        return long_description
    except:
        return None

setup(
    name="botasaurus_driver",
    version='4.0.66',
    description="Super Fast, Super Anti-Detect, and Super Intuitive Web Driver",
    long_description_content_type="text/markdown",
    long_description=get_description(),
    author="Chetan",
    author_email="chetan@omkar.cloud",
    maintainer="Chetan",
    maintainer_email="chetan@omkar.cloud",
    license="MIT",
    python_requires=">=3.5",
    keywords=[
        "webdriver", "browser", "captcha", "web-scraping",
        "selenium", "navigator", "python3", "cloudflare",
        "anti-delect", "anti-bot", "bot-detection",
        "cloudflare-bypass", "distil", "anti-detection"
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Internet :: WWW/HTTP :: Browsers",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    install_requires=[
        "requests",
        "deprecated",
        "psutil",
        "botasaurus-proxy-authentication",
        "websocket-client>=1.8.0",
        "pyvirtualdisplay"
    ],
    url="https://github.com/omkarcloud/botasaurus-driver",
    project_urls={
        "Homepage": "https://github.com/omkarcloud/botasaurus-driver",
        "Bug Reports": "https://github.com/omkarcloud/botasaurus-driver/issues",
        "Source": "https://github.com/omkarcloud/botasaurus-driver"
    },
    packages=find_packages(include=["botasaurus_driver"]),
    include_package_data=True,
)
