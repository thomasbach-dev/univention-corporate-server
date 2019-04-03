#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Copyright 2004-2019 Univention GmbH
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
# <http://www.gnu.org/licenses/>.

import re
import univention.admin.syntax  # Liefert standard Syntax-Definitionen für die UDM 'property_descriptions' unten

# Für das Einbinden von Übersetzungskatalogen für verschiedene Sprachen
translation = univention.admin.localization.translation('univention.admin.handlers.test')
_ = translation.translate


# <Syntax definitions>
# FIXME: don't define syntaxes in modules
class SynVoIP_Protocols(univention.admin.syntax.select):

	"""Diese Klasse definiert einen neue Syntax für eine Auswahlliste von VoIP-Protokollen"""
	# der Text, der in dem Web-Frontend vor die Auswahlliste geschrieben werden soll
	name = _(u'VoIP_Protocol')

	# die Liste der Auswahlmöglichkeiten: Jedes der Elemente enthält einen eindeutigen Schlüssel
	# und den anzuzeigenden Text
	choices = [('sip', u'SIP'), ('h323', u'H.323'), ('skype', u'Skype')]


class SynVoIP_Address(univention.admin.syntax.simple):

	"""Diese Klasse dient als Syntax für VoIP Adresse. Der Aufbau ist einer E-Mail Adresse ähnlich,
	kann aber als Präfix noch ein Schema gefolgt von einem ':' enthalten.
	Valide Schemta sind: sip, h323 und skype"""

	name = _('VoIP_Address')
	min_length = 4
	max_length = 256
	_re = re.compile('((^(sip|h323|skype):)?([a-zA-Z])[a-zA-Z0-9._-]+)@[a-zA-Z0-9._-]+$')

	def parse(self, text):
		if self._re.match(text) is not None:
			return text
		raise univention.admin.uexceptions.valueError(_(u'Not a valid VoIP Address'))


# </Syntax definitions>

# <UDM module API>

# interner Name des Moduls, verwendet auch im Kommandozeilen-Client
module = 'test/ip_phone'
# dieses Objekt kann keine Unterobjekte enthalten
childs = 0
# ein sprechender Name für das Web-Frontend
short_description = _(u'IP-Phone')
# eine ausführliche Beschreibung
long_description = _(u'An example module for the Univention Directory Manager')
# die LDAP Operationen, die auf diesem Objekt ausgeführt werden können
operations = ['add', 'edit', 'remove', 'search', 'move']


# Um einen eigenen Wizard zu erstellen, der im UDM-Web links in der Navigationsleiste erscheint:
# usewizard = 1
# wizardmenustring = "VoIP"
# wizarddescription =  _(u"Add, delete and search VoIP objects"
# wizardoperations = { 'add' : [_(u"add"), _(u"Add an VoIP object")],
# 'find' : [_(u"Search"), _(u"Search VoIP objects"]) }
# wizardpath = "univentionUsersObject"

# <UDM module options>
# Liste der Optionen für dieses Modul, bzw. für den behandelten Objekttyp
options = {
	# durch 'options' werden optionale Eigenschaften eines Objekts definiert
	'default': univention.admin.option(
		objectClasses=['top', 'testPhone']
	),
	'redirection': univention.admin.option(
		short_description=_('Call redirect option'),
		default=True,
		editable=True,
		objectClasses=['testPhoneCallRedirect'],
	)
}

# <UDM module properties>

# Liste der Eigenschaften für dieses Modul
property_descriptions = {
	# der eindeutige Name eines IP-Telefons
	'name': univention.admin.property(
		short_description=_(u'Name'),
		long_description=_(u'ID of the IP-phone'),
		syntax=univention.admin.syntax.hostName,  # Eigenschaft muss der Syntax eines Rechnernamens entsprechen, Def. in syntax.py
		multivalue=False,
		options=[],
		required=True,  # Eigenschaft muss angegeben werden
		may_change=False,  # Eigenschaft darf nach Erstellung nicht verändert werden
		identifies=True,  # Eigenschaft muss eindeutig sein
	),
	'active': univention.admin.property(
		short_description=_(u'active'),
		long_description=_(u'The IP-phone can be deactivated'),
		syntax=univention.admin.syntax.TrueFalseUp,  # Definition in syntax.py, kompatibel zur LDAP Boolean Syntax
		multivalue=False,
		options=[],
		required=False,  # Eigenschaft muss nicht zwingend angegeben werden
		default='TRUE',  # Eigenschaft ist standardmäßig aktiviert
		may_change=True,  # Eigenschaft darf modifiziert werden
		identifies=False
	),
	'protocol': univention.admin.property(
		short_description=_(u'Protocol'),
		long_description=_(u'Supported VoIP protocols'),
		syntax=SynVoIP_Protocols,  # nutzt die selbst definierte Auswahlliste als Syntax
		multivalue=False,
		options=[],
		required=False,
		default='sip',  # der Eintrag 'sip' ist vorausgewählt
		may_change=True,
		identifies=False
	),
	'ip': univention.admin.property(
		short_description=_(u'IP-Address'),
		long_description=_(u'IP-Address of the IP-phone'),
		syntax=univention.admin.syntax.ipAddress,  # muss der Syntax einer IP (Version 4) Adresse entsprechen
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'priuser': univention.admin.property(
		short_description=_(u'Primary User'),
		long_description=_(u'The primary user of this IP-phone'),
		syntax=SynVoIP_Address,  # muss der Syntax einer VoIP Adresse entsprechen
		multivalue=False,
		options=[],
		required=True,
		may_change=True,
		identifies=False
	),
	'users': univention.admin.property(
		short_description=_(u'Additional Users'),
		long_description=_(u'Users, that may register with this phone'),
		syntax=SynVoIP_Address,  # jeder Eintrag muss der Syntax einer VoIP Adresse entsprechen
		multivalue=True,  # Dies ist eine Liste von Adressen
		options=[],
		required=False,
		may_change=True,
		identifies=False
	),
	'redirect_user': univention.admin.property(
		short_description=_(u'Redirection User'),
		long_description=_(u'Address for call redirection'),
		syntax=SynVoIP_Address,
		multivalue=False,
		options=['redirection'],  # Ist nur da, wenn die Option gesetzt ist
		required=False,
		may_change=True,
		identifies=False
	),
}

# <UDM module layout>

# Das 'layout' definiert die Anordung der Felder im Web-Frontend.
# Jeder 'univention.admin.tab' entspricht einem Reiter:
# * Der erste Parameter ist der Name des Reiters und der zweite Parameter
# ist eine Beschreibung der Einstellungsmöglich für diesen Reiter
# * Die folgende Liste definiert die Anordnung der einzelnen Eigenschaftsfelder.
# * Per advanced=True wird der Reiter nur angezeigt, wenn das Anzeigen der
# erweiterten Einstellungen aktiviert ist.
layout = [
	univention.admin.tab(_(u'General'), _(u'Basic Settings'), [
		[univention.admin.field("name"), univention.admin.field("active")],
		[univention.admin.field("ip"), univention.admin.field("protocol")],
		[univention.admin.field("priuser")],
	]),
	univention.admin.tab(_(u'Advanced'), _(u'Advanced Settings'), [
		[univention.admin.field("users")],
	], advanced=True),
	univention.admin.tab(_(u'Redirect'), _(u'Redirect Option'), [
		[univention.admin.field("redirect_user")],
	], advanced=True),
]

# <Mapping of UDM properties to LDAP attribute>

# Das 'mapping' Objekt definiert die Abbildung der Eigenschaften des UDM-Moduls/Objekts auf Attribute eines LDAP-Objektes
mapping = univention.admin.mapping.mapping()
# Abbindung der Eigenschaft 'name' auf den RDN, nutzt vordefinierte Mapping-Funktion aus mapping.py:
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
# mapping.register der Eigenschaft 'active' auf das LDAP-Attribut testPhoneActive:
mapping.register('active', 'testPhoneActive', None, univention.admin.mapping.ListToString)
# Abbindung der Eigenschaft 'protocol' auf das LDAP-Attribut testPhoneProtocol:
mapping.register('protocol', 'testPhoneProtocol', None, univention.admin.mapping.ListToString)
mapping.register('ip', 'testPhoneIP', None, univention.admin.mapping.ListToString)
mapping.register('priuser', 'testPhonePrimaryUser', None, univention.admin.mapping.ListToString)
# Abbindung der Eigenschaft 'users' ohne weitere Übersetzung direkt auf das LDAP-Attribut testPhoneUsers:
mapping.register('users', 'testPhoneUsers')
mapping.register('redirect_user', 'testPhoneRedirectUser', None, univention.admin.mapping.ListToString)


class object(univention.admin.handlers.simpleLdap):

	u"""Dieses Objekt unterstützt den Univention Directory Manager bei LDAP-Operationen,
	die sich auf dieses Modul beziehen.
	Die Basisklasse univention.admin.handlers.simpleLdap implementiert die komplette Kommunikation über LDAP,
	so dass hier nur die Anpassungen für dieses spezielle LDAP-Objekt implementiert werden müssen.
	Dafür bietet die Basisklasse jeweils eine Funktionen um vor und nach einer LDAP Operation
	Anpassungen vorzunehmen. In dieser Beispielklasse werden die Prototypen all dieser Funktionen definiert,
	um einen Überblick der Möglichkeiten zu geben."""

	# den Modulnamen als Attribute der Klasse übernehmen (oben definiert als module='test/ip-phone')
	module = module


lookup = object.lookup


def identify(dn, attr, canonical=False):
	u"""Prüft ob die verwaltete Objektklasse diese Moduls in der übergebenen Liste enthalten ist,
	d.h. ob dieses Modul für die Handhabung des Objekts zuständig ist."""
	return 'testPhone' in attr.get('objectClass', [])
