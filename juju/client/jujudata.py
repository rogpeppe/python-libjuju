import os
import yaml
import pathlib
import io

from juju import tag
import juju.client.client as jujuclient
from juju.client.gocookies import GoCookieJar
from juju.errors import JujuError


class JujuData:
    '''Provide access to the Juju client configuration files.
    Any configuration file is read once and then cached.'''
    def __init__(self):
        self.path = os.environ.get('JUJU_DATA') or '~/.local/share/juju'
        self.path = os.path.abspath(os.path.expanduser(self.path))
        # _loaded keeps track of the loaded YAML from
        # the Juju data files so we don't need to load the same
        # file many times.
        self._loaded = {}

    def refresh(self):
        '''Forget the cache of configuration file data'''
        self._loaded = {}

    def current_controller(self):
        '''Return the current controller name'''
        return self._load_yaml('controllers.yaml', 'current-controller')

    def current_model(self, controller_name=None):
        '''Return the current model, qualified by its controller name.
        If controller_name is specified, the current model for
        that controller will be returned.
        '''
        # TODO respect JUJU_MODEL environment variable.
        if not controller_name:
            controller_name = self.current_controller()
        if not controller_name:
            raise JujuError('No current controller')
        models = self.models()[controller_name]
        if 'current-model' not in models:
            return None
        return controller_name + ':' + models['current-model']

    def parse_model(self, model):
        """Split the given model_name into controller and model parts.
        If the controller part is empty, the current controller will be used.
        If the model part is empty, the current model will be used for
        the controller.
        The returned model name will always be qualified with a username.
        :param model str: The model name to parse.
        :return (str, str): The controller and model names.
        """
        # TODO if model is empty, use $JUJU_MODEL environment variable.
        if model and ':' in model:
            # explicit controller given
            controller_name, model_name = model.split(':')
        else:
            # use the current controller if one isn't explicitly given
            controller_name = self.current_controller()
            model_name = model
        if not controller_name:
            controller_name = self.current_controller()
        if not model_name:
            model_name = self.current_model(controller_name)

        if '/' not in model_name:
            # model name doesn't include a user prefix, so add one
            # by using the current user for the controller.
            accounts = self.accounts().get('controller_name')
            if accounts is None:
                raise JujuError('No account found for controller {}'.format(controller_name))
            username = accounts.get['user']
            if username is None:
                raise JujuError('No username found for controller {}'.format(controller_name))
            model_name = username + "/" + model_name

        return controller_name, model_name

    def load_credential(self, cloud, name=None):
        """Load a local credential.

        :param str cloud: Name of cloud to load credentials from.
        :param str name: Name of credential. If None, the default credential
            will be used, if available.
        :return: A CloudCredential instance, or None.
        """
        try:
            cloud = tag.untag('cloud-', cloud)
            creds_data = self.credentials()[cloud]
            if not name:
                default_credential = creds_data.pop('default-credential', None)
                default_region = creds_data.pop('default-region', None)  # noqa
                if default_credential:
                    name = creds_data['default-credential']
                elif len(creds_data) == 1:
                    name = list(creds_data)[0]
                else:
                    return None, None
            cred_data = creds_data[name]
            auth_type = cred_data.pop('auth-type')
            return name, jujuclient.CloudCredential(
                auth_type=auth_type,
                attrs=cred_data,
            )
        except (KeyError, FileNotFoundError):
            return None, None

    def controllers(self):
        return self._load_yaml('controllers.yaml', 'controllers')

    def models(self):
        return self._load_yaml('models.yaml', 'controllers')

    def accounts(self):
        return self._load_yaml('accounts.yaml', 'controllers')

    def credentials(self):
        return self._load_yaml('credentials.yaml', 'credentials')

    def _load_yaml(self, filename, key):
        if filename in self._loaded:
            # Data already exists in the cache.
            return self._loaded[filename].get(key)
        # TODO use the file lock like Juju does.
        filepath = os.path.join(self.path, filename)
        with io.open(filepath, 'rt') as f:
            data = yaml.safe_load(f)
            self._loaded[filename] = data
            return data.get(key)

    def cookies_for_controller(self, controller_name):
        f = pathlib.Path(self.path) / 'cookies' / controller_name
        if not f.exists():
            f = pathlib.Path('~/.go-cookies').expanduser()
            # TODO if neither cookie file exists, where should
            # we create the cookies?
        return GoCookieJar(str(f))
