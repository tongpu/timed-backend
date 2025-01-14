import redminelib
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Case, Count, Sum, When

from timed.projects.models import Project


class Command(BaseCommand):
    help = "Update expenditures on associated Redmine projects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pretend",
            action="store_true",
            help="Pretend mode for testing",
        )

    def handle(self, *args, **options):
        redmine = redminelib.Redmine(
            settings.REDMINE_URL,
            key=settings.REDMINE_APIKEY,
        )

        affected_projects = (
            Project.objects.filter(
                archived=False,
                redmine_project__isnull=False,
            )
            .annotate(count_reports=Count("tasks__reports"))
            .annotate(
                total_hours=Case(
                    When(count_reports__gt=0, then=Sum("tasks__reports__duration")),
                    default=None,
                )
            )
        )

        pretend = options["pretend"]

        for project in affected_projects.iterator():
            estimated_hours = (
                project.estimated_time.total_seconds() / 3600
                if project.estimated_time
                else 0.0
            )
            total_spent_hours = (
                project.total_hours.total_seconds() / 3600
                if project.total_hours
                else 0.0
            )
            try:
                issue = redmine.issue.get(project.redmine_project.issue_id)
            except redminelib.exceptions.BaseRedmineError as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed retrieving Project {project.name} with Redmine issue {project.redmine_project.issue_id} assigned. Skipping.\n{e}"
                    )
                )
                continue
            issue.estimated_hours = estimated_hours
            # fields not active in Redmine projects settings won't be saved
            issue.custom_fields = [
                {
                    "id": settings.REDMINE_SPENTHOURS_FIELD,
                    "value": total_spent_hours,
                },
                {
                    "id": settings.REDMINE_AMOUNT_OFFERED_FIELD,
                    "value": project.amount_offered.amount,
                },
                {
                    "id": settings.REDMINE_AMOUNT_INVOICED_FIELD,
                    "value": project.amount_invoiced.amount,
                },
            ]
            if not pretend:
                try:
                    issue.save()
                    continue
                except redminelib.exceptions.BaseRedmineError as e:  # pragma: no cover
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to save Project {project.name} with Redmine issue {issue.id}!\n{e}"
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Updating Redmine issue {project.redmine_project.issue_id} with total spent hours {total_spent_hours}, amount offered {project.amount_offered.amount}, amount invoiced {project.amount_invoiced.amount}"
                )
            )
