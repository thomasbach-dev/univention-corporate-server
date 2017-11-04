# -*- coding: utf-8 -*-
#
# Copyright 2017 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import os
import grp
import pwd
import stat
import os.path
import listener
import univention.admin.uldap

from univention.listener.handler_logging import get_logger
try:
	from typing import Dict, List, Tuple, Optional
	import logging
	import univention.admin.uldap.access
	import univention.admin.uldap.position
	from univention.listener.handler import ListenerModuleHandler
except ImportError:
	pass


listener.configRegistry.load()


class ListenerModuleConfigurationError(Exception):
	pass


class ListenerModuleConfiguration(object):
	"""
	Interface class for accessing the configuration and code of a listener
	module.

	Subclass this and set the class attributes or pass them through __init__.
	If more logic is needed, overwrite the corresponding
	get_<attribute> method. Setting "name", "ldap_filter" and
	"listener_module_class" is mandatory.

	To extend the configuration, add key names in get_configuration_keys()
	and create a get_<attribute> method.

	The listener server will use an object of your subclass to access your
	listener module through:
	1. get_configuration()
	2. get_listener_module_instance()
	"""

	name = ''  # type: str                         # (*) name of the listener module
	description = ''  # type: str                  # description of the listener module
	ldap_filter = ''  # type: str                  # (*) LDAP filter, if matched will trigger the listener module
	attributes = []  # type: List[str]             # only trigger module, if any of the listed attributes has changed
	modules_to_run_before = []  # type: List[str]  # list of names of module to run before this one
	modules_to_run_after = []  # type: List[str]   # list of names of module to run after this one
	run_asynchronously = False  # type: bool       # run module in the background
	parallelism = 1  # type: int                   # run multiple instances of module in parallel (implies run_asynchronously)
	listener_module_class = None  # type: type     # (*) class that implements the module
	# (*) required

	_po_cache = dict()  # type: Dict[str, univention.admin.uldap.position]

	def __init__(self, *args, **kwargs):  # type: (*Tuple, **Dict) -> None
		self._lo = None  # type: univention.admin.uldap.access
		self._logger = None  # type: logging.Logger
		_keys = self.get_configuration_keys()
		for k, v in kwargs.items():
			if k in _keys:
				setattr(self, k, kwargs.pop(k))

	def __repr__(self):
		return '{}({})'.format(
			self.__class__.__name__,
			', '.join('{}={!r}'.format(k, v)for k, v in self.get_configuration().items()))

	def get_configuration(self):  # type: () -> dict
		"""
		Get the configuration of a listener module.

		:return: dict
		"""
		res = dict()
		for key in self.get_configuration_keys():
			getter = getattr(self, 'get_{}'.format(key), None)
			if getter and callable(getter):
				value = getter()
			else:
				if hasattr(self, key):
					self.logger.warn("No 'get_%s' method found, using value of attribute %r directly.", key, key)
					value = getattr(self, key)
				else:
					raise ListenerModuleConfigurationError('No get_* method or class attribute found for configuration key %r.', key)
			res[key] = value
		return res

	@classmethod
	def get_configuration_keys(cls):  # type: () -> list
		return [
			'attributes',
			'description',
			'ldap_filter',
			'listener_module_class',
			'modules_to_run_after',
			'modules_to_run_before',
			'name',
			'parallelism',
			'run_asynchronously'
		]

	def get_name(self):  # type: () -> str
		if not self.name:
			raise ListenerModuleConfigurationError('Missing name.')
		return self.name

	def get_description(self):  # type: () -> str
		return self.description

	def get_ldap_filter(self):  # type: () -> str
		if not self.ldap_filter:
			raise ListenerModuleConfigurationError('Missing ldap_filter.')
		return self.ldap_filter

	def get_attributes(self):  # type: () -> list
		return self.attributes

	def get_modules_to_run_before(self):  # type: () -> list
		return self.modules_to_run_before

	def get_modules_to_run_after(self):  # type: () -> list
		return self.modules_to_run_after

	def get_parallelism(self):  # type: () -> int
		return self.parallelism

	def get_run_asynchronously(self):  # type: () -> bool
		return self.run_asynchronously

	def get_listener_module_instance(self, *args, **kwargs):  # type: (*Tuple, **Dict) -> ListenerModuleHandler
		"""
		Get an instance of the listener module.

		:param args: tuple: passed to __init__ of ListenerModuleHandler
		:param kwargs: dict: : passed to __init__ of ListenerModuleHandler
		:return: instance of ListenerModuleHandler
		"""
		return self.get_listener_module_class()(self, *args, **kwargs)

	def get_listener_module_class(self):  # type: () -> type
		"""
		Get the class to instantiate for a listener module.

		:return: type: subclass of univention.listener.ListenerModuleHandler
		"""
		if not self.listener_module_class:
			raise ListenerModuleConfigurationError('Missing listener_module_class.')
		else:
			return self.listener_module_class

	def get_active(self):  # type: () -> bool
		"""
		If this listener module should run. Detemined by the value of
		listener/module/<name>/deactivate.

		:return: bool
		"""
		return not listener.configRegistry.is_true('listener/module/{}/deactivate'.format(self.get_name()), False)

	@property
	def lo(self):  # type: () -> univention.admin.uldap.access
		"""
		Get a LDAP access object.

		:return: univention.admin.uldap.access object
		"""
		if not self._lo:
			raise ListenerModuleConfigurationError('LDAP connection of listener module %r has not yet been initialized.')
		return self._lo()

	@property
	def po(self):  # type: () -> univention.admin.uldap.position
		"""
		Get a LDAP position object for the base DN (ldap/base).

		:return: univention.admin.uldap.position object
		"""
		return self.get_ldap_position(self.lo.base)

	@classmethod
	def get_ldap_position(cls, ldap_position=listener.configRegistry['ldap/base']):  # type: (str) -> univention.admin.uldap.position
		"""
		Get a LDAP position object.

		:param ldap_position: str: DN
		:return: univention.admin.uldap.position object
		"""
		if ldap_position not in cls._po_cache:
			cls._po_cache[ldap_position] = univention.admin.uldap.position(ldap_position)
		return cls._po_cache[ldap_position]

	@property
	def logger(self):  # type: () -> logging.Logger
		if not self._logger:
			file_name = self.get_name().replace('/', '_')
			logger_name = self.get_name().replace('.', '_')
			log_dir = '/var/log/univention/listener_modules'
			file_path = os.path.join(log_dir, '{}.log'.format(file_name))
			listener_uid = pwd.getpwnam('listener').pw_uid
			adm_grp = grp.getgrnam('adm').gr_gid
			if not os.path.isdir(log_dir):
				old_uid = os.geteuid()
				try:
					if old_uid != 0:
						listener.setuid(0)
					os.mkdir(log_dir)
					os.chown(log_dir, listener_uid, adm_grp)
					os.chmod(log_dir, stat.S_ISGID | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
				finally:
					if old_uid != 0:
						listener.unsetuid()
			self._logger = get_logger(logger_name, target=file_path)
		return self._logger

	def set_ldap_credentials(self, base_dn, bind_dn, bind_pw, ldap_server):  # type: (str, str, str, str) -> None
		"""
		This method is intended for the listener server to set the connection
		credentials (for cn=admin). This will create a univention.admin.uldap.access
		object from them and make it accessible through self.lo.

		:param base_dn: str
		:param bind_dn: str
		:param bind_pw: str
		:param ldap_server: str
		:return: None
		"""
		self._lo = lambda: univention.admin.uldap.access(
			host=ldap_server,
			base=base_dn,
			binddn=bind_dn,
			bindpw=bind_pw)
