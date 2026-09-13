"""Run real concurrency checks in a disposable peer-authenticated PostgreSQL cluster."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
bindir=Path(subprocess.check_output(['pg_config','--bindir'],text=True).strip())
with tempfile.TemporaryDirectory(prefix='ampve-postgres-fixture-',dir='/tmp') as temporary:
    root=Path(temporary);data=root/'data';socket=root/'socket';socket.mkdir(mode=0o700)
    subprocess.run([str(bindir/'initdb'),'-D',str(data),'--auth-local=peer','--auth-host=reject','--no-locale','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run([str(bindir/'pg_ctl'),'-D',str(data),'-l',str(root/'server.log'),'-w','start','-o',
        f"-c listen_addresses='' -c unix_socket_directories='{socket}' -p 55433 -c shared_buffers=32MB"],check=True,stdout=subprocess.DEVNULL)
    try:
        environment={**os.environ,'AMPVE_TESTING':'1','AMPVE_POSTGRES_TEST_SOCKET':str(socket)}
        subprocess.run([sys.executable,str(ROOT/'apps/platform/manage.py'),'test',
            'workspace.test_deployment_concurrency.DeploymentConcurrencyTests','workspace.test_deployments.DeploymentTests',
            '--settings=config.postgresql_test','--noinput'],check=True,env=environment,cwd=ROOT)
    finally:
        subprocess.run([str(bindir/'pg_ctl'),'-D',str(data),'-w','stop','-m','fast'],check=True,stdout=subprocess.DEVNULL)
print('Isolated PostgreSQL lifecycle/concurrency tests passed; the temporary cluster was stopped and removed.')
