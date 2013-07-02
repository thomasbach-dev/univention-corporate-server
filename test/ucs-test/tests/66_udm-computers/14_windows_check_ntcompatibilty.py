#!/usr/share/ucs-test/runner python
## desc: Validate handling of "ntCompatibility" attribute in computers/windows module
## tags: [udm-computers]
## roles: [domaincontroller_master]
## exposure: careful
## packages:
##   - univention-config
##   - univention-directory-manager-tools


import smbpasswd
import univention.testing.udm as udm_test
import univention.testing.strings as uts
import univention.testing.utils as utils
import univention.config_registry as configRegistry


if __name__ == '__main__':
	windowsHostName = uts.random_string()
	
	with udm_test.UCSTestUDM() as udm:
		windowsHost = udm.create_object('computers/windows', name = windowsHostName, ntCompatibility = '1')
		if not utils.verify_ldap_object( windowsHost, {'sambaNTPassword': [ smbpasswd.nthash(windowsHostName.lower()) ]} ):
			utils.fail()
