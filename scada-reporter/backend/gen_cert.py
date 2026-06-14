"""
OPC UA client certificate generator for KEPServerEX compatibility.
Matches properties of the existing trusted cert in KEPServerEX PKI store.
"""
import datetime
import os
import struct
import sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

OUT = "C:/project/smart/scada-reporter/backend/certs"
APP_URI = "urn:SCADA-Reporter:UA-Client"
HOSTNAME = "B110RPSRV2"

os.makedirs(OUT, exist_ok=True)

# 2048-bit RSA key
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

subject = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "SCADA Reporter OPC UA Client"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SCADA Reporter"),
    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Engineering"),
])

now = datetime.datetime.utcnow()
cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(subject)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=3650))
    # Key usage matching existing KEPServerEX-trusted cert
    .add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=True,
            key_encipherment=True,
            data_encipherment=True,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    )
    # Both serverAuth and clientAuth (matching existing cert)
    .add_extension(
        x509.ExtendedKeyUsage([
            ExtendedKeyUsageOID.SERVER_AUTH,
            ExtendedKeyUsageOID.CLIENT_AUTH,
        ]),
        critical=False,
    )
    # CA:True (since key_cert_sign=True)
    .add_extension(
        x509.BasicConstraints(ca=True, path_length=None),
        critical=True,
    )
    # OPC UA requires URI in SAN
    .add_extension(
        x509.SubjectAlternativeName([
            x509.UniformResourceIdentifier(APP_URI),
            x509.DNSName("localhost"),
            x509.DNSName(HOSTNAME),
        ]),
        critical=False,
    )
    .add_extension(
        x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
        critical=False,
    )
    .add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)

# Write PEM files
pem_path = f"{OUT}/client.pem"
key_path = f"{OUT}/client_key.pem"
der_path = f"{OUT}/client.der"

with open(pem_path, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

with open(key_path, "wb") as f:
    f.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))

with open(der_path, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.DER))

# Calculate SHA1 thumbprint for KEPServerEX
der_bytes = cert.public_bytes(serialization.Encoding.DER)
import hashlib
thumbprint = hashlib.sha1(der_bytes).hexdigest()

print(f"Certificate generated:")
print(f"  PEM: {pem_path}")
print(f"  Key: {key_path}")
print(f"  DER: {der_path}")
print(f"  Thumbprint (SHA1): {thumbprint}")
print(f"  Valid until: {cert.not_valid_after_utc}")
print(f"  SAN URI: {APP_URI}")
print()
print(f"Copy DER to KEPServerEX trusted store with name: {thumbprint}.der")
