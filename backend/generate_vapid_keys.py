"""Generate a Web Push VAPID key pair without persisting secrets.

Run from the backend environment after dependencies are installed:

    python generate_vapid_keys.py

Copy the printed values directly into Render environment secrets. Do not redirect
this output into a tracked file and never commit the private key.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DEFAULT_SUBJECT = "https://nordicsignal.8pnwk5r8f4.workers.dev"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_vapid_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_value = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_value = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return {
        "public_key": _b64url(public_value),
        "private_key": _b64url(private_value),
    }


def main():
    pair = generate_vapid_pair()
    print("Generate these once and keep the private value secret.\n")
    print(f"NORDICSIGNAL_VAPID_PUBLIC_KEY={pair['public_key']}")
    print(f"NORDICSIGNAL_VAPID_PRIVATE_KEY={pair['private_key']}")
    print(f"NORDICSIGNAL_VAPID_SUBJECT={DEFAULT_SUBJECT}")
    print("\nDo not commit these values. Regenerating the pair invalidates existing push subscriptions.")


if __name__ == "__main__":
    main()
