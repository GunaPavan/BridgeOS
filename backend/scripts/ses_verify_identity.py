"""Ops script — trigger SES verify-identity email + list verified identities.

Usage:
    python -m scripts.ses_verify_identity --email pavan@example.com
    python -m scripts.ses_verify_identity --list

Once the recipient clicks the link AWS sends, ``send_email(...)`` works.

Run this BEFORE setting ``SES_FROM_EMAIL`` so the from-address is verified.
The recipient address ALSO needs verification (SES is in sandbox mode).
"""

from __future__ import annotations

import argparse
import sys

from app.integrations import ses_client


def main() -> int:
    p = argparse.ArgumentParser(description="SES verify + list identities.")
    p.add_argument("--email", help="Email to verify (sends verify link)")
    p.add_argument("--list", action="store_true", help="List verified identities")
    args = p.parse_args()

    if args.list:
        result = ses_client.list_verified_identities()
        print("mode:", result.get("mode"))
        for ident in result.get("identities", []):
            print(f"  {ident}")
        if result.get("error"):
            print("error:", result["error"])
            return 1
        return 0

    if not args.email:
        p.print_help()
        return 1

    result = ses_client.verify_email_identity(args.email)
    print("ok:" , result.get("ok"))
    print("mode:", result.get("mode"))
    if result.get("error"):
        print("error:", result["error"])
        return 1
    print(f"verification email sent to {args.email}. Click the link to enable sending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
