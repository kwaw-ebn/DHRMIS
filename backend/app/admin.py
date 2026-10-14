"""Operator-only MFA recovery. Run in a trusted environment after identity verification."""
import argparse, secrets
from .db import SessionLocal
from .models import User, Session, Audit
from .security import ph

def main():
    parser=argparse.ArgumentParser();parser.add_argument('email');parser.add_argument('--reason',required=True);parser.add_argument('--reset-password',action='store_true');args=parser.parse_args()
    with SessionLocal() as db:
        user=db.query(User).filter(User.email==args.email.lower()).one()
        user.totp_secret=None;user.mfa_enabled=False;user.last_totp_step=-1;user.failed_attempts=0;user.locked_until=None
        temporary=None
        if args.reset_password:
            temporary=secrets.token_urlsafe(20);user.password_hash=ph.hash(temporary);user.must_change_password=True
        db.query(Session).filter(Session.user_id==user.id).delete()
        db.add(Audit(actor_name='Trusted infrastructure operator',action='MFA_RECOVERY',entity_id=user.id,detail=args.reason[:500]));db.commit()
        if temporary: print('Temporary password (share privately): '+temporary)
        print('MFA cleared and sessions revoked. The next login requires MFA enrollment.')
if __name__=='__main__':main()
