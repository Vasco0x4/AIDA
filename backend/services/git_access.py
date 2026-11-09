"""Authorization is checked at queue time and again at download time."""
from models.git_connection import GitConnection, GitRepository
from services.git_provider import GitError, GitProvider


def binding(db, project_id, lock=False):
    grant = db.query(GitRepository).filter_by(project_id=project_id).first()
    if not grant:
        return None
    query = db.query(GitConnection).filter_by(id=grant.connection_id)
    connection = (query.with_for_update().populate_existing() if lock else query).first()
    if lock:
        db.refresh(grant)
    if not grant.allowed or not connection or not connection.enabled or not connection.token_encrypted:
        raise GitError('Git access to this project is disabled. Ask an administrator to allow the repository in Integrations.')
    return grant, connection


def fetch_connected(project_id, ref, session_factory):
    with session_factory() as db:
        result = binding(db, project_id)
        if not result:
            raise GitError('Git repository connection is missing.')
        grant, connection = result
        provider, ident = GitProvider(connection), grant.provider_id
    return provider.fetch(ident, ref)
