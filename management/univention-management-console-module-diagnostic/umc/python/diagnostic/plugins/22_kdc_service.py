#!/usr/bin/python2.7
# coding: utf-8
#
# Univention Management Console module:
#  System Diagnosis UMC module
#
# Copyright 2016-2020 Univention GmbH
#
# https://www.univention.de/
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
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.

import struct
import socket
import random
import datetime

import ipaddr
import dns.resolver
import dns.exception
from pyasn1.type import tag
from pyasn1.type import char
from pyasn1.type import univ
from pyasn1.type.univ import noValue
from pyasn1.type import useful
from pyasn1.type import namedtype
from pyasn1.type import constraint
import pyasn1.codec.der.encoder as encoder
import pyasn1.codec.der.decoder as decoder
import pyasn1.error
from univention.config_registry import handler_set as ucr_set
import univention.config_registry
from univention.management.console.modules.diagnostic import Warning, Critical, ProblemFixed, MODULE
from univention.management.console.modules.diagnostic import util

import argparse
import logging
import sys
from binascii import unhexlify

from impacket.krb5 import constants
from impacket.krb5.types import Principal

from univention.lib.i18n import Translation
_ = Translation('univention-management-console-module-diagnostic').translate

title = _('KDC service check')
description = ['The check for the KDC reachability was successful.']
run_descr = ["Performs a KDC reachability check"]

# This checks for the reachability of KDCs by sending a AS-REQ per TCP and UDP.
# The AS-REQ is send with the fake user `kdc-reachability-check`. The KDCs will
# respond in several ways: either with an KRB-ERROR (PREAUTH_REQUIRED,
# PRINCIPAL_UNKNOWN or RESPONSE_TO_BIG) or a AS-REP with an anonymous ticket.
#
# If we do not receive one of the above, the connection is not accepted, the
# socket is closed or an operation times out, we can assume, that the KDCs is
# not reachable.
#
# This check will test the KDCs as specified in UCR `kerberos/kdc` with TCP and
# UDP on port 88. If `kerberos/defaults/dns_lookup_kdc` is set, KDC discovery as
# specified in section `7.2.3. KDC Discovery on IP Networks` [1] will be used.
# In this case the ports as specified in the SRV records are used.
#
# This implements a minimal number of packages as defined in [1] and does not
# rely on python-kerberos or python-krb5, as those are too high level and
# outdated.
#
# Reachability checks of kpasswd servers are not implemented, as those are a
# separate protocol. See [2].
#
# [1]: https://tools.ietf.org/html/rfc4120
# [2]: https://tools.ietf.org/html/rfc3244

class Int32(univ.Integer):
	subtypeSpec = univ.Integer.subtypeSpec + constraint.ValueRangeConstraint(
		-2147483648, 2147483647)


def _msg_type_component(tag_value, values):
	c = constraint.ConstraintsUnion(
		*(constraint.SingleValueConstraint(int(v)) for v in values))
	return _sequence_component('msg-type', tag_value, univ.Integer(),
							   subtypeSpec=c)

def _sequence_component(name, tag_value, type, **subkwargs):
	return namedtype.NamedType(name, type.subtype(
		explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple,
							tag_value),
		**subkwargs))

def _sequence_optional_component(name, tag_value, type, **subkwargs):
	return namedtype.OptionalNamedType(name, type.subtype(
		explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple,
							tag_value),
		**subkwargs))
class Microseconds(univ.Integer):
	subtypeSpec = univ.Integer.subtypeSpec + constraint.ValueRangeConstraint(
		0, 999999)

class EncryptedData(univ.Sequence):
	componentType = namedtype.NamedTypes(
		_sequence_component("etype", 0, Int32()),
		_sequence_optional_component("kvno", 1, univ.Integer()),
		_sequence_component("cipher", 2, univ.OctetString())
		)

def _application_tag(tag_value):
	return univ.Sequence.tagSet.tagExplicitly(
		tag.Tag(tag.tagClassApplication, tag.tagFormatConstructed,
				int(tag_value)))

def _vno_component(tag_value, name="pvno"):
	return _sequence_component(
		name, tag_value, univ.Integer(),
		subtypeSpec=constraint.ValueRangeConstraint(5, 5))

class PA_DATA(univ.Sequence):
	componentType = namedtype.NamedTypes(
		_sequence_component('padata-type', 1, Int32()),
		_sequence_component('padata-value', 2, univ.OctetString())
		)


class PrincipalName(univ.Sequence):
	componentType = namedtype.NamedTypes(
		_sequence_component("name-type", 0, Int32()),
		_sequence_component("name-string", 1,
							univ.SequenceOf(componentType=char.GeneralString()))
							)


class KDC_REQ_BODY(univ.Sequence):
	componentType = namedtype.NamedTypes(
		_sequence_component('kdc-options', 0, univ.BitString()),
		_sequence_optional_component('cname', 1, PrincipalName()),
		_sequence_component('realm', 2, char.GeneralString()),
		_sequence_optional_component('sname', 3, PrincipalName()),
		_sequence_optional_component('from', 4, useful.GeneralizedTime()),
		_sequence_component('till', 5, useful.GeneralizedTime()),
		_sequence_component('nonce', 7, univ.Integer()),
		_sequence_component('etype', 8,
							univ.SequenceOf(componentType=Int32())),
		)

class AS_REQ(univ.Sequence):
	tagSet = _application_tag(constants.ApplicationTagNumbers.AS_REQ.value)
	componentType = namedtype.NamedTypes(
		_vno_component(1),
		_msg_type_component(2, (constants.ApplicationTagNumbers.AS_REQ.value,
								constants.ApplicationTagNumbers.TGS_REQ.value)),
		_sequence_optional_component('padata', 3,
									 univ.SequenceOf(componentType=PA_DATA())),
		_sequence_component('req-body', 4, KDC_REQ_BODY())
		)

def seq_set(seq, name, builder=None, *args, **kwargs):
	component = seq.setComponentByName(name).getComponentByName(name)
	if builder is not None:
		seq.setComponentByName(name, builder(component, *args, **kwargs))
	else:
		seq.setComponentByName(name)
	return seq.getComponentByName(name)

def seq_set_iter(seq, name, iterable):
	component = seq.setComponentByName(name).getComponentByName(name)
	for pos, v in enumerate(iterable):
		component.setComponentByPosition(pos, v)

class SessionError(Exception):
	"""
	This is the exception every client should catch regardless of the underlying
	SMB version used. We'll take care of that. NETBIOS exceptions are NOT included,
	since all SMB versions share the same NETBIOS instances.
	"""
	def __init__( self, error = 0, packet=0):
		Exception.__init__(self)
		self.error = error
		self.packet = packet

	def getErrorCode( self ):
		return self.error

	def getErrorPacket( self ):
		return self.packet

	def getErrorString( self ):
		return nt_errors.ERROR_MESSAGES[self.error]

	def __str__( self ):
		if self.error in nt_errors.ERROR_MESSAGES:
			return 'SMB SessionError: %s(%s)' % (nt_errors.ERROR_MESSAGES[self.error])
		else:
			return 'SMB SessionError: 0x%x' % self.error

class KerberosError(SessionError):
	"""
	This is the exception every client should catch regardless of the underlying
	SMB version used. We'll take care of that. NETBIOS exceptions are NOT included,
	since all SMB versions share the same NETBIOS instances.
	"""
	def __init__( self, error = 0, packet=0):
		SessionError.__init__(self)
		self.error = error
		self.packet = packet
		if packet != 0:
			self.error = self.packet['error-code']
	   
	def getErrorCode( self ):
		return self.error

	def getErrorPacket( self ):
		return self.packet

	def getErrorString( self ):
		return constants.ERROR_MESSAGES[self.error]

	def __str__( self ):
		retString = 'Kerberos SessionError: %s(%s)' % (constants.ERROR_MESSAGES[self.error])
		try:
			# Let's try to get the NT ERROR, if not, we quit and give the general one
			if self.error == constants.ErrorCodes.KRB_ERR_GENERIC.value:
				eData = decoder.decode(self.packet['e-data'], asn1Spec = KERB_ERROR_DATA())[0]
				nt_error = struct.unpack('<L', eData['data-value'].asOctets()[:4])[0]
				retString += '\nNT ERROR: %s(%s)' % (nt_errors.ERROR_MESSAGES[nt_error])
		except:
			pass

		return retString


class KRB_ERROR(univ.Sequence):
	tagSet = _application_tag(constants.ApplicationTagNumbers.KRB_ERROR.value)
	componentType = namedtype.NamedTypes(
		_vno_component(0),
		_msg_type_component(1, (constants.ApplicationTagNumbers.KRB_ERROR.value,)),
		_sequence_optional_component('ctime', 2, useful.GeneralizedTime()),
		_sequence_optional_component('cusec', 3, Microseconds()),
		_sequence_component('stime', 4, useful.GeneralizedTime()),
		_sequence_component('susec', 5, Microseconds()),
		_sequence_component('error-code', 6, Int32()),
		_sequence_optional_component('crealm', 7, char.GeneralString()),
		_sequence_optional_component('cname', 8, PrincipalName()),
		_sequence_component('realm', 9, char.GeneralString()),
		_sequence_component('sname', 10, PrincipalName()),
		_sequence_optional_component('e-text', 11, char.GeneralString()),
		_sequence_optional_component('e-data', 12, univ.OctetString())
		)


def send_and_receive(kdc, port, protocol, as_req):
	socket_type = socket.SOCK_DGRAM if protocol == 'udp' else socket.SOCK_STREAM
	sock = socket.socket(socket.AF_INET, socket_type)
	sock.settimeout(1)

	if protocol == 'tcp':
		packed = struct.pack('!i', len(as_req)) + as_req
	else:
		packed = as_req

	try:
		sock.connect((kdc, port))
		sock.sendall(packed)
	except (socket.error, socket.timeout):
		raise
		sock.close()
		raise ServerUnreachable()

	received = ''
	num_received = 0
	if protocol == 'udp':  # fake the length field
		received += '\x00\x00\x00\x00'
		num_received += 4
	while num_received < 128:
		try:
			(buf, addr) = sock.recvfrom(128)
		except (socket.error, socket.timeout):
			buf = ''
		if not buf:
			break
		received += buf
		num_received += len(buf)

	if not received:
		raise EmptyResponse()

	return received

def sendReceive(data, host, kdcHost, port, prot):
	socktype = socket.IPPROTO_IP if prot == 'udp' else socket.SOCK_STREAM
	if prot == 'tcp':
		messageLen = struct.pack('!i', len(data))
	try:
		outlist = []
		af, socket_type, proto, canonname, sa = socket.getaddrinfo(kdcHost, port, socket.AF_UNSPEC, socktype)[0]
		#p =socket.getprotobyname('udp')
		#p2 =socket.getprotobyname('tcp')
		s = socket.socket(af, socket_type)
		s.settimeout(1)
		s.connect(sa)
	except socket.error as e:
		s.close()
		raise socket.error("Connection error (%s:%s)" % (kdcHost, port), e)

	if prot == 'tcp':
		s.sendall(messageLen + data)
	else:
		s.sendall(data)

	recvDataLen = struct.unpack('!i', s.recv(4))[0]

	r = s.recv(recvDataLen)
	while len(r) < recvDataLen:
		r += s.recv(recvDataLen-len(r))

	try:
		krbError = KerberosError(packet = decoder.decode(r, asn1Spec = KRB_ERROR())[0])
	except:
		raise

	if krbError.getErrorCode() not in [0, 6, 14, 24, 25, 52, 60]: #!= constants.ErrorCodes.KDC_ERR_PREAUTH_REQUIRED.value:
		raise krbError

	return r


def make_as_req(clientName, password, domain, kdc, port, prot):

	asReq = AS_REQ()

	domain = domain.upper()
	serverName = Principal('krbtgt/%s'%domain, type=constants.PrincipalNameType.NT_PRINCIPAL.value)  

	asReq['pvno'] = 5
	asReq['msg-type'] =  int(constants.ApplicationTagNumbers.AS_REQ.value)

	asReq['padata'] = noValue
	asReq['padata'][0] = noValue
	asReq['padata'][0]['padata-type'] = int(constants.PreAuthenticationDataTypes.PA_PAC_REQUEST.value)
	asReq['padata'][0]['padata-value'] = noValue #encodedPacRequest

	reqBody = seq_set(asReq, 'req-body')

	reqBody['kdc-options'] = [0 for i in range(0,32)]

	seq_set(reqBody, 'sname', serverName.components_to_asn1)
	seq_set(reqBody, 'cname', clientName.components_to_asn1)

	if domain == '':
		raise Exception('Empty Domain not allowed in Kerberos')

	reqBody['realm'] = domain

	reqBody['till'] = '19700101000000Z'
	reqBody['nonce'] = random.SystemRandom().getrandbits(31)


	supportedCiphers = (int(constants.EncryptionTypes.aes256_cts_hmac_sha1_96.value),)

	seq_set_iter(reqBody, 'etype', supportedCiphers)

	message = encoder.encode(asReq)
	try:
		#r = sendReceive(kdc, port, prot)
		r = sendReceive(message, domain, kdc, port, prot)
		return r
	except KerberosError as e:
		raise

def resolve_kdc_record(protocol, domainname):
		kerberos_dns_fqdn = '_kerberos._{}.{}'.format(protocol, domainname)
		try:
			result = dns.resolver.query(kerberos_dns_fqdn, 'SRV')
		except dns.exception.DNSException:
			result = list()

		for record in result:
			yield (record.target.to_text(True), record.port, protocol)


def run(_umc_instance, retest=False):
	configRegistry = univention.config_registry.ConfigRegistry()
	configRegistry.load()

	target_realm = configRegistry.get('kerberos/realm')
	username = 'kdc-reachability-check'

	kdc_fqds = configRegistry.get('kerberos/kdc', '').split()
	ns_lookup_kdc = configRegistry.is_true('kerberos/defaults/dns_lookup_kdc', True)

	if not kdc_fqds or dns_lookup_kdc:
			domainname = configRegistry.get('domainname')
			kdc_to_check = list(resolve_kdc_record('tcp', domainname))
			kdc_to_check.extend(resolve_kdc_record('udp', domainname))
	else:
		kdc_to_check = [(kdc, 88, 'tcp') for kdc in kdc_fqds]
		kdc_to_check.extend((kdc, 88, 'udp') for kdc in kdc_fqds)
	username = Principal(username, type=1)
	r = make_as_req(username, '', target_realm, kdc_to_check[1][0], kdc_to_check[1][1], kdc_to_check[0][2])
#	for kdc, port, prot in kdc_to_check:
#		r = make_as_req(username, '', target_realm, kdc, port, prot)



if __name__ == '__main__':
	from univention.management.console.modules.diagnostic import main
	main()

