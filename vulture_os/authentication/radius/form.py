#!/home/vlt-os/env/bin/python
"""This file is part of Vulture OS.

Vulture OS is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Vulture OS is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Vulture OS.  If not, see http://www.gnu.org/licenses/.
"""
__author__ = "Kevin GUILLEMOT"
__credits__ = []
__license__ = "GPLv3"
__version__ = "4.0.0"
__maintainer__ = "Vulture OS"
__email__ = "contact@vultureproject.org"
__doc__ = 'RadiusRepository dedicated form class'

# Django system imports
from django.conf import settings
from django.core.validators import RegexValidator
from django.forms import CheckboxInput, ModelForm, NumberInput, PasswordInput, Select, TextInput

# Django project imports
from authentication.radius.models import RadiusRepository

# Extern modules imports
from re import match as re_match

# Required exceptions imports
from django.forms import ValidationError

# Logger configuration imports
import logging
logging.config.dictConfig(settings.LOG_SETTINGS)
logger = logging.getLogger('gui')


class RadiusRepositoryForm(ModelForm):

    class Meta:
        model = RadiusRepository
        fields = ('name', 'host', 'port', 'nas_id', 'secret', 'retry', 'timeout')
        widgets = {
            'name': TextInput(attrs={'class': 'form-control'}),
            'host': TextInput(attrs={'class': 'form-control'}),
            'port': NumberInput(attrs={'class': 'form-control'}),
            'nas_id': TextInput(attrs={'class': 'form-control'}),
            'secret': TextInput(attrs={'class': 'form-control'}),
            'retry': NumberInput(attrs={'class': 'form-control'}),
            'timeout': NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove the blank input generated by django
        if not self.initial.get('name'):
            self.fields['name'].initial = "RADIUS Repository"

    def clean_name(self):
        """ Replace all spaces by underscores to prevent bugs later """
        return self.cleaned_data['name'].replace(' ', '_')

    def clean_host(self):
        value = self.cleaned_data.get('host')
        RegexValidator('^[A-Za-z0-9-.]*$', value)
        return value
