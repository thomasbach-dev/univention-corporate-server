#!/bin/sh

# before running this script install the new Scalix packages into a Scalix VM

IP=10.200.8.120

# 1. fetch the diverted scripts from the VM
filelist=''
for file in $(find ../opt -type f ! -regex .*svn.*); do
	filelist="${file/../}.real\n$filelist"
done
echo -e ${filelist} | rsync --files-from=- ${IP}:/ .

for file in $(find opt -type f); do
	mv $file ${file%.real}
done

for patch in univention-patches/*; do
	patch < $patch
done

for file in $(find opt -type f); do
	diff $file ../$file > $file.diff
done

# 2. check the diverted configuration templates for modifications
# TODO: diff the output against a univention-patches file
ssh ${IP} 'cd /var/opt/scalix/??/; find -name "*.dpkg-dist" | while read line; do echo "Checking $line"; diff -u ${line%.dpkg-dist} $line; echo "***"; done' > static_conffiles.diff

# now check the diffs visually
