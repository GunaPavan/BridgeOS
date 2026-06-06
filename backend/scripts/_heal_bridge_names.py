"""One-off: rename Bridge rows whose name contains control chars from the
raw Blood Warriors hex bridge_id (e.g. ``Bridge \\xb6eba1``). Uses the
linked Patient.name to build a clean human-readable label."""

from __future__ import annotations

from app.db import SessionLocal
from app.models import Bridge, Patient


def main() -> int:
    fixed = 0
    sample = []
    with SessionLocal() as db:
        bridges = db.query(Bridge).all()
        for b in bridges:
            if not b.name:
                continue
            # Heuristic: if any non-printable character is present, rename
            has_garbage = any(ord(c) < 32 or ord(c) > 126 for c in b.name)
            looks_like_raw_hex = "\\x" in b.name
            if has_garbage or looks_like_raw_hex:
                patient = db.get(Patient, b.patient_id)
                if patient:
                    b.name = f"Bridge for {patient.name}"
                    fixed += 1
        db.commit()
        for b in db.query(Bridge).limit(5).all():
            sample.append(repr(b.name))
    print(f"Healed {fixed} bridge names")
    for s in sample:
        print(" ", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
