from django.core.management.base import BaseCommand
from workspace.deployment_services import reconcile_deployments


class Command(BaseCommand):
    help='Expire queued approvals and flag missing update reports without inferring a device outcome.'

    def handle(self,*args,**options):
        self.stdout.write(f'Reconciled {reconcile_deployments()} pending firmware deployments. No device writes performed.')
