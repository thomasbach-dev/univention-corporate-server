in the directory with the deb files


echo all deb files whose package is already installed
for p in $(find . -name "*.deb"); do dpkg -s $(dpkg --info $p | awk '/Package/ { print $2 }') &>/dev/null && echo "$p"; done


install all deb files whose package is already installed
for p in $(find . -name "*.deb"); do dpkg -s $(dpkg --info $p | awk '/Package/ { print $2 }') &>/dev/null && dpkg -i "$p"; done
