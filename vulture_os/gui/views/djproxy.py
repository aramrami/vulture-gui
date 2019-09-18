#!/home/vlt-os/env/bin/python
"""This file is part of Vulture 3.

Vulture 3 is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Vulture 3 is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Vulture 3.  If not, see http://www.gnu.org/licenses/.
"""

__author__ = "Jérémie JOURDIN"
__credits__ = []
__license__ = "GPLv3"
__version__ = "4.0.0"
__maintainer__ = "Vulture OS"
__email__ = ""
__doc__ = ''

from djproxy.views import HttpProxy
from toolkit.network.network import get_management_ip

class proxy_netdata(HttpProxy):
    base_url = 'http://{}:19999/'.format(get_management_ip())


class proxy_console(HttpProxy):
    base_url = 'http://{}:4200/'.format(get_management_ip())

class proxy_haproxy(HttpProxy):
    base_url = 'http://{}:1978/stats/'.format(get_management_ip())