from cryptography.x509 import CertificateBuilder, Name, NameAttribute
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import datetime


# 生成私钥
def generate_private_key():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    return private_key


# 生成证书
def generate_self_signed_cert(private_key):
    subject = issuer = Name([
        NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        NameAttribute(NameOID.ORGANIZATION_NAME, u"Example Corp"),
        NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])

    cert = CertificateBuilder(
        subject_name=subject,
        issuer_name=issuer,
        public_key=private_key.public_key(),
        serial_number=1000,
        not_valid_before=datetime.datetime.utcnow(),
        not_valid_after=datetime.datetime.utcnow() + datetime.timedelta(days=365),
        extensions=[]
    ).sign(private_key, hashes.SHA256())

    return cert


# 保存私钥和证书
def save_cert_and_key(cert, private_key):
    # 保存私钥
    with open("server.key", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # 保存证书
    with open("server.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


if __name__ == "__main__":
    private_key = generate_private_key()
    cert = generate_self_signed_cert(private_key)
    save_cert_and_key(cert, private_key)
    print("证书和私钥已生成并保存在 'server.pem' 和 'server.key'")
