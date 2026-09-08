from app.models.asset import Asset
from app.models.audit_log import AuditLog
from app.models.ticket import Ticket
from app.models.user import User

# BackupLog usa um banco/engine próprio (backup_meta.db), separado do Base
# principal, então não faz parte deste create_all — veja app/db/backup_session.py.
