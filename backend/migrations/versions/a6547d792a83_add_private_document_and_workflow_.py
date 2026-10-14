"""Add private document and workflow reminder references."""
from alembic import op
import sqlalchemy as sa
revision='a6547d792a83'
down_revision='a852d77d150b'
branch_labels=None
depends_on=None
def upgrade():
    with op.batch_alter_table('notifications') as batch:
        batch.add_column(sa.Column('document_id',sa.String(36),nullable=True))
        batch.add_column(sa.Column('event_key',sa.String(300),nullable=True))
        batch.create_unique_constraint('uq_notification_event_key',['event_key'])
        batch.create_foreign_key('fk_notification_document','employee_documents',['document_id'],['id'])
def downgrade():
    with op.batch_alter_table('notifications') as batch:
        batch.drop_constraint('fk_notification_document',type_='foreignkey')
        batch.drop_constraint('uq_notification_event_key',type_='unique')
        batch.drop_column('event_key')
        batch.drop_column('document_id')
