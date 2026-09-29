"""TLS context creation and local-development certificate generation."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
from pathlib import Path
import ssl
import stat
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from common.config import Settings
from common.secrets import get_private_key_password


class TLSConfigurationError(RuntimeError):
    """Raised when TLS material is unavailable or cannot be loaded safely."""


def _minimum_tls_context(purpose: ssl.Purpose) -> ssl.SSLContext:
    context = ssl.create_default_context(purpose)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def create_server_context(settings: Settings) -> ssl.SSLContext:
    if not settings.cert_file.is_file() or not settings.key_file.is_file():
        raise TLSConfigurationError(
            "TLS certificate or private key is missing. Set the password environment variable and run "
            "`python generate_cert.py`, or configure production certificate paths."
        )

    password = get_private_key_password(settings.key_password_env)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(
            certfile=str(settings.cert_file),
            keyfile=str(settings.key_file),
            password=password,
        )
    except (OSError, ssl.SSLError) as exc:
        raise TLSConfigurationError(f"Unable to load TLS certificate and encrypted private key: {exc}") from exc
    return context


def create_client_context(settings: Settings) -> ssl.SSLContext:
    if not settings.ca_file.is_file():
        raise TLSConfigurationError(
            f"Trusted CA/certificate file was not found: {settings.ca_file}. Refusing an unverified connection."
        )
    try:
        context = _minimum_tls_context(ssl.Purpose.SERVER_AUTH)
        context.load_verify_locations(cafile=str(settings.ca_file))
    except (OSError, ssl.SSLError) as exc:
        raise TLSConfigurationError(f"Unable to load trusted certificate: {exc}") from exc
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _subject_alternative_names(hosts: Iterable[str]) -> x509.SubjectAlternativeName:
    names: list[x509.GeneralName] = []
    for host in dict.fromkeys(host.strip() for host in hosts if host.strip()):
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    if not names:
        raise ValueError("At least one certificate hostname or IP address is required.")
    return x509.SubjectAlternativeName(names)


def generate_development_certificate(
    cert_file: Path,
    key_file: Path,
    password: str,
    hosts: Iterable[str],
    valid_days: int = 365,
) -> None:
    """Create an encrypted, self-signed leaf certificate for local development only."""
    if len(password) < 12:
        raise ValueError("The private-key password must contain at least 12 characters.")
    if not 1 <= valid_days <= 825:
        raise ValueError("Certificate validity must be between 1 and 825 days.")
    if cert_file.exists() or key_file.exists():
        raise FileExistsError("Refusing to overwrite existing TLS material. Remove it deliberately before regenerating.")

    cert_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = dt.datetime.now(dt.timezone.utc)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Local Development"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=valid_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(_subject_alternative_names(hosts), critical=False)
        .sign(private_key, hashes.SHA256())
    )

    key_file.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
        )
    )
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
