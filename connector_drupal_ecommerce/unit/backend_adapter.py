# -*- coding: utf-8 -*-
###########################################################################
#    Module Writen to OpenERP, Open Source Management Solution
#
#    Copyright (c) 2015 OpenPyme - http://www.openpyme.mx/
#    All Rights Reserved.
#    Coded by: Agustín Cruz (agustin.cruz@openpyme.mx)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###########################################################################

from __future__ import division

import requests
import logging
import json

from datetime import datetime

from openerp.addons.connector.unit.backend_adapter import CRUDAdapter

_logger = logging.getLogger(__name__)


class WrongContent(requests.exceptions.RequestException):
    """The response has the wrong content."""


class URLNotFound(requests.exceptions.HTTPError):
    """Special error for deal with URL Not Found"""


class AccessDenied(requests.exceptions.HTTPError):
    """Special error for deal with 403 messages"""


class DrupalServices(object):
    """Drupal services class.

    config is a nice way to deal with configuration files."""
    def __init__(self, config):
        self.base_url = config['base_url'].strip()
        # remove left '/' if any
        self.endpoint = config['endpoint'].strip().lstrip('/')
        self.username = config['username'].strip()
        self.password = config['password'].strip()
        self.timeout = config['timeout']

        # set other things
        self.services_link = "%s/%s" % (self.base_url, self.endpoint)

        # Create session for this object and store headers
        self.session = requests.Session()
        self.session.headers.update(
            {'User-Agent': 'OpenERP', 'Content-Type': 'application/json'}
        )

    def request(self, directive, params, method='get'):
        """ Make request to Drupal services.
        See https://www.drupal.org/node/783254 for a list of RESTful directives
        :param directive: eg system/connect.json, node/1.json, variable_get.json
        :param params: data in python {}
        :param method: GET, POST, PUT, DELETE, etc.
        :return: the JSON object from Drupal services.
        :exception: HTTPError
        """
        data = None
        link = "%s/%s" % (self.services_link, directive)

        if method == 'get':
            if params is not None:
                data = params
        elif method == 'post' or method == 'put':
            if params is not None:
                data = json.dumps(params)

        # process request
        _logger.debug('Making connection to: %s' % link)

        # this is the actually connection.
        response = getattr(self.session, method)(
            link, data=data, timeout=self.timeout
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                raise AccessDenied
            elif e.response.status_code == 404:
                raise URLNotFound
            else:
                raise Exception(
                    e.message + ' ' + response.text.encode('utf-8')
                )
        # Decode json response or raise error
        try:
            response = response.json()
        except ValueError:
            _logger.error(response.text)
            raise WrongContent(response=response.text)
        return response

    def user_login(self):
        """
        Login user
        """
        params = {'username': self.username, 'password': self.password}
        result = self.request('user/login.json', params, 'post')
        if 'token' in result and len(result['token']) > 0:
            self.session.headers.update({'X-CSRF-Token': result['token']})
            _logger.info('User login successful: %s' % self.username)
        else:
            _logger.error('User login failed: %s' % self.username)

    def user_logout(self):
        self.request('user/logout.json', None, 'post')
        _logger.info('User logout successful: %s' % self.username)


class DrupalCRUDAdapter(CRUDAdapter):
    """ External Records Adapter for Drupal """
    _model_name = None
    _drupal_model = None
    _drupal_node_type = None

    def __init__(self, environment):
        """
        :param environment: current environment (backend, session, ...)
        :type environment: :py:class:`connector.connector.Environment`
        """
        super(DrupalCRUDAdapter, self).__init__(environment)
        backend = self.backend_record
        drupal = DrupalServices(
            {'base_url': backend.url,
             'endpoint': backend.endpoint,
             'username': backend.username,
             'password': backend.password,
             'timeout':  backend.timeout}
        )
        self.drupal = drupal
        # Login user for be able to do next operations
        self.drupal.user_login()

    def _call(self, directive, params=None, method='get'):
        """ Execute a request from Drupal services """
        return self.drupal.request(directive + '.json', params, method)

    def create(self, data):
        """ Create a record on the external system """
        return self._call(self._drupal_model, data, 'post')

    def read(self, id, attributes=None):
        """ Returns the information of a record
        :rtype: dict
        """
        try:
            return self._call('/'.join([self._drupal_model, id]))
        except URLNotFound:
            # Object not found in Drupal return True
            return

    def write(self, id, data):
        """ Update records on the external system """
        return self._call('/'.join([self._drupal_model, id]), data, 'put')

    def delete(self, id):
        try:
            return self._call(
                '/'.join([self._drupal_model, id]), method='delete',
            )
        except (URLNotFound, AccessDenied):
            # Drupal raise errors 403 or 404 when try delete a record
            # that have been already deleted. As the result is the same we
            # were trying to accomplish, simply ignore message and
            # keep moving forward
            return

    def search(self, filters=None):
        """ Search records based on some filters """
        return self._call(self._drupal_model, filters, 'get')

    def totimestamp(self, dt, epoch=datetime(1970, 1, 1)):
        """ Helper function to convert date objects to timestamp """
        td = dt - epoch
        return (td.microseconds + (td.seconds + td.days * 86400) * 10 ** 6) / 10 ** 6
