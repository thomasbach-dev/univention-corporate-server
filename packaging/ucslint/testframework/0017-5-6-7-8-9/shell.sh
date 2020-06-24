#!/bin/bash
univention-ldapsearch "(&(objectclass=univentionDomainController)(univentionService=Samba 4))" cn | sed -n 's/^cn: \(.*\)/\1/p'
univention-ldapsearch "uid=Administrator" | ldapsearch-wrapper
declare -a args=()
args[${#args[@]}]="-D"
cat /etc/fstab | grep '^[^#]'
univention-ldapsearch -o ldif-wrap=no '(uid=Administrator)' 1.1 | grep ^dn | sed -ne 's/^dn: //p'
