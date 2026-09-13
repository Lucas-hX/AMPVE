"""Run with the isolated PostgreSQL fixture harness, never the deployed database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
import uuid
from django.db import connection, close_old_connections
from django.test import TransactionTestCase, Client
from .models import FirmwareDeployment, FirmwareDeploymentEvent, DeviceFirmware
from . import deployment_services as service
from . import test_deployments as fixtures


@skipUnless(connection.vendor=='postgresql','Requires the isolated PostgreSQL runner')
class DeploymentConcurrencyTests(TransactionTestCase):
    release=fixtures.DeploymentTests.release
    running=fixtures.DeploymentTests.running
    api=fixtures.DeploymentTests.api
    queue=fixtures.DeploymentTests.queue
    report=fixtures.DeploymentTests.report
    rebooting=fixtures.DeploymentTests.rebooting

    def setUp(self):
        fixtures.DeploymentTests.setUpTestData.__func__(type(self))
        fixtures.DeploymentTests.setUp(self)

    def race(self,functions):
        barrier=Barrier(len(functions))
        def run(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(run,functions))

    def test_same_request_id_creates_exactly_one_job(self):
        key=uuid.uuid4()
        ids=self.race([lambda:self.queue(key).pk,lambda:self.queue(key).pk])
        self.assertEqual(ids[0],ids[1]);self.assertEqual(FirmwareDeployment.objects.count(),1)
        self.assertEqual(FirmwareDeploymentEvent.objects.count(),1)

    def test_different_requests_cannot_create_conflicting_jobs(self):
        def queue():
            try:self.queue();return 'queued'
            except service.DeploymentError:return 'conflict'
        self.assertEqual(sorted(self.race([queue,queue])),['conflict','queued'])
        self.assertEqual(FirmwareDeployment.objects.count(),1)

    def test_cancel_and_download_claim_have_one_serialized_winner(self):
        job=self.queue()
        data={'release_id':job.release_id,'sequence':1,'state':'downloading','bytes_written':0,
              'app_sha256':job.previous_app_sha256,'boot_confirmed':True,'error_code':''}
        def claim():
            return Client().post(f'/api/devices/v1/{self.device.pk}/updates/{job.pk}/report/',data,
                content_type='application/json',HTTP_AUTHORIZATION='Bearer '+self.token).status_code
        def cancel():
            try:service.cancel_update(self.owner,self.device.pk,job.pk);return 'cancelled'
            except service.DeploymentError:return 'started'
        result=self.race([claim,cancel]);job.refresh_from_db()
        self.assertIn((result[0],result[1],job.state),[(200,'started','downloading'),(409,'cancelled','cancelled')])

    def test_concurrent_confirmation_replay_only_advances_once(self):
        job=self.rebooting()
        data={'release_id':job.release_id,'sequence':4,'state':'confirmed','bytes_written':self.target.policy['app']['size'],
              'app_sha256':self.target.policy['app']['sha256'],'boot_confirmed':True,'error_code':''}
        def confirm():
            return Client().post(f'/api/devices/v1/{self.device.pk}/updates/{job.pk}/report/',data,
                content_type='application/json',HTTP_AUTHORIZATION='Bearer '+self.token).status_code
        self.assertEqual(self.race([confirm,confirm]),[200,200])
        self.assertEqual(FirmwareDeploymentEvent.objects.filter(deployment=job,sequence=4).count(),1)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,2)

    def test_fresh_process_recovers_pending_state_without_guessing_an_outcome(self):
        import os
        import subprocess
        import sys
        from datetime import timedelta
        from django.conf import settings
        from django.utils import timezone
        job=self.rebooting()
        FirmwareDeployment.objects.filter(pk=job.pk).update(updated_at=timezone.now()-timedelta(minutes=16))
        subprocess.run([sys.executable,str(settings.REPO_DIR/'apps/platform/manage.py'),
            'reconcile_firmware_deployments','--settings=config.postgresql_test'],check=True,
            env={**os.environ,'AMPVE_POSTGRES_USE_TEST_DATABASE':'1'},stdout=subprocess.DEVNULL)
        job.refresh_from_db()
        self.assertEqual(job.state,'rebooting');self.assertTrue(job.needs_attention)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,1)
