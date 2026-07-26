"""QD Server API routes."""

from fastapi import APIRouter

from qd_server.api.auth import router as auth_router
from qd_server.api.templates import router as templates_router
from qd_server.api.template_sources import router as template_sources_router
from qd_server.api.tasks import router as tasks_router
from qd_server.api.task_groups import router as task_groups_router
from qd_server.api.plugins import router as plugins_router
from qd_server.api.notifications import router as notifications_router
from qd_server.api.notepad import router as notepad_router
from qd_server.api.test_request import router as test_router
from qd_server.api.migrate import router as migrate_router
from qd_server.api.admin import router as admin_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(templates_router, prefix="/templates", tags=["Templates"])
api_router.include_router(template_sources_router, prefix="/template-sources", tags=["TemplateSources"])
api_router.include_router(task_groups_router, prefix="/task-groups", tags=["TaskGroups"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(plugins_router, prefix="/plugins", tags=["Plugins"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(notepad_router, prefix="/notepad", tags=["Notepad"])
api_router.include_router(test_router, prefix="/test", tags=["Test"])
api_router.include_router(migrate_router, prefix="/migrate", tags=["Migrate"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])
