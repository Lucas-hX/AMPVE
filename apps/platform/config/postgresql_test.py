"""Only for the ephemeral local cluster created by tests/postgres/deployments.py."""
from .settings import *
import getpass

socket = Path(os.environ['AMPVE_POSTGRES_TEST_SOCKET']).resolve()
if not TESTING or not str(socket).startswith('/tmp/ampve-postgres-fixture-') or socket.name != 'socket':
    raise RuntimeError('Use the isolated PostgreSQL fixture runner; never point tests at a deployed database.')
DATABASES = {'default':{'ENGINE':'django.db.backends.postgresql','NAME':'postgres','USER':getpass.getuser(),
    'HOST':str(socket),'PORT':'55433','TEST':{'NAME':'ampve_test_deployments'}}}
if os.environ.get('AMPVE_POSTGRES_USE_TEST_DATABASE')=='1':
    DATABASES['default']['NAME']='ampve_test_deployments'
