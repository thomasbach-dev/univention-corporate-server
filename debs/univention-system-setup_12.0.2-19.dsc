Format: 1.0
Source: univention-system-setup
Binary: univention-system-setup, univention-system-setup-boot, di-univention-system-setup, univention-management-console-module-setup
Architecture: any all
Version: 12.0.2-19
Maintainer: Univention GmbH <packages@univention.de>
Standards-Version: 3.8.2
Build-Depends: debhelper (>= 9), ucslint-univention, dh-python, python-all, python3-all, univention-config-dev, univention-management-console-dev (>= 11.0.4-37), univention-ucs-translation-template, python-apt, python-psutil, python-notifier, python-univention-lib, python-univention-management-console, python-univention-appcenter, python-imaging, python-dnspython, unzip, po-debconf (>= 0.5.0), python-lxml, stylus
Package-List:
 di-univention-system-setup udeb debian-installer standard arch=any
 univention-management-console-module-setup deb univention optional arch=all
 univention-system-setup deb univention optional arch=all
 univention-system-setup-boot deb univention optional arch=all
Checksums-Sha1:
 8072105da9db9fee324549a31d65a8dd6c9b0cdb 3055251 univention-system-setup_12.0.2-19.tar.gz
Checksums-Sha256:
 089e3975f411bf4fa37ae4d179fc006fea64311a8c9dfbfd7a30a7bbac41fefd 3055251 univention-system-setup_12.0.2-19.tar.gz
Files:
 7b2873e7352a3e1b0c02e9305d65645c 3055251 univention-system-setup_12.0.2-19.tar.gz
