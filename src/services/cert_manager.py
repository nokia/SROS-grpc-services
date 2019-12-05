############################################################################
#
#   Filename:           cert_lib.py
#
#   Author:             Martin Tibensky
#   Created:            Thu Nov 21 12:00:34 CET 2019
#
#   Description:        .
#
#
############################################################################
#
#              Copyright (c) 2019 Nokia
#
############################################################################
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.base import load_pem_x509_certificate, load_pem_x509_csr
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import NameOID

from collections import OrderedDict
from datetime import timedelta, datetime
import uuid
from six import text_type

# notes for docs:
#   this works only with x509 pem encoded certificates
#   add directory setting for persistent storage of certs to shell???


class CertificateManager:
    def __init__(self):
        self.certs = OrderedDict()

    def __str__(self):
        certs = ""
        for cert in self.certs:
            certs += "\n{0}".format(self.certs[cert])
        return certs

    def __getitem__(self, key):
        return self.certs[key]

    def __contains__(self, key):
        return key in self.certs

    def add_certificate(self, name=None, certificate=None):
        if not name or not certificate:
            raise ValueError("name and certificate has to be specified")
        self.certs[name] = certificate

    def get_certificate(self, name=None):
        if name not in self.certs:
            raise ValueError(
                "certificate with name {} not present in manger".format(name)
            )
        return self.certs[name]

    def remove_certificate(self, name=None):
        if name not in self.certs:
            raise ValueError(
                "certificate with name {} not present in manger".format(name)
            )
        del self.certs[name]


class Certificate:
    def __init__(self, name=None):
        self.name = name
        self.csr = None
        self.private_key = None
        self.pem_csr = None
        self.pem_private_key = None
        self.pem_certificate = None

    def __str__(self):
        significant_args = [
            "hostname",
            "create_ca",
            "key_size",
            "common_name",
            "country",
            "state",
            "city",
            "organization",
            "organizational_unit",
            "ip_addr_list",
            "email_id",
            "serial_number",
            "not_valid_before_days",
            "not_valid_after_days",
            "certificate_dir",
        ]
        _str = "{} {}\n".format(self.__class__.__name__, self.name)
        for arg in significant_args:
            try:
                _str += "\t{} = {}\n".format(arg, getattr(self, arg))
            except AttributeError:
                pass

        return _str

    def certificate_params(
        self,
        hostname=None,
        key_size=2048,
        common_name=None,
        country=None,
        state=None,
        city=None,
        organization=None,
        organizational_unit=None,
        ip_addr_list=None,
        email_id=None,
        serial_number=None,
        not_valid_before_days=None,
        not_valid_after_days=None,
        certificate_dir=None,
    ):
        self.hostname = hostname
        self.key_size = key_size
        self.common_name = common_name
        self.country = country
        self.state = state
        self.city = city
        self.organization = organization
        self.organizational_unit = organizational_unit
        self.ip_addr_list = ip_addr_list
        self.email_id = email_id
        self.serial_number = serial_number
        self.not_valid_before_days = not_valid_before_days
        self.not_valid_after_days = not_valid_after_days
        self.certificate_dir = certificate_dir

    def save_pem(self, entity_type=None, path=None):
        if not path:
            raise ValueError("Path has to be specified")

        if entity_type == "certificate":
            text = self.pem_certificate
        elif entity_type == "csr":
            text = self.pem_csr
        elif entity_type == "key":
            text = self.pem_private_key
        else:
            raise ValueError("Unsupported entity_type {}".format(entity_type))

        if not text:
            raise ValueError(
                "{} is not loaded in this certificate object".format(
                    entity_type
                )
            )

        with open(path, "wb") as fd:
            fd.write(text)

    def load_pem(
        self, entity_type=None, path=None, pem_text=None, password=None
    ):
        """ Load pem encoded entity

        Attributes:
            entity_type (str): certificate|key|csr.
            path (str): Absolute path to file containing pem encoded entity.
            pem_text (str): String object with pem encoded entity
            password (str): Password to use in case entity is protected
        """
        if path and pem_text:
            raise ValueError("Path and pem_text are mutually exclusive")

        if path:
            with open(path, "rb") as f:
                pem_text = f.read()

        if entity_type == "certificate":
            return load_pem_x509_certificate(
                pem_text, backend=default_backend()
            )
        elif entity_type == "csr":
            return load_pem_x509_csr(pem_text, backend=default_backend())
        elif entity_type == "key":
            return load_pem_private_key(
                pem_text, password=password, backend=default_backend(),
            )
        else:
            raise ValueError("Unsupported entity_type {}".format(entity_type))

    @property
    def subject_name(self):
        attribute_list = []
        if self.common_name:
            attribute_list.append(
                x509.NameAttribute(
                    NameOID.COMMON_NAME, text_type(self.common_name)
                )
            )
        if self.organization:
            attribute_list.append(
                x509.NameAttribute(
                    NameOID.ORGANIZATION_NAME, text_type(self.organization)
                )
            )
        if self.organizational_unit:
            attribute_list.append(
                x509.NameAttribute(
                    NameOID.ORGANIZATIONAL_UNIT_NAME,
                    text_type(self.organizational_unit),
                )
            )
        if self.country:
            attribute_list.append(
                x509.NameAttribute(
                    NameOID.COUNTRY_NAME, text_type(self.country)
                )
            )
        if self.state:
            attribute_list.append(
                x509.NameAttribute(
                    NameOID.STATE_OR_PROVINCE_NAME, text_type(self.state)
                )
            )
        if self.city:
            attribute_list.append(
                x509.NameAttribute(NameOID.LOCALITY_NAME, text_type(self.city))
            )
        if self.email_id:
            attribute_list.append(
                x509.NameAttribute(
                    NameOID.EMAIL_ADDRESS, text_type(self.email_id)
                )
            )
        return x509.Name(attribute_list)

    @property
    def subject_alt_name(self):
        return x509.SubjectAlternativeName(
            [x509.DNSName(text_type(addr)) for addr in self.ip_addr_list]
        )

    @property
    def serial_num(self):
        return self.serial_number if self.serial_number else int(uuid.uuid4())

    @property
    def not_valid_before_date(self):
        return datetime.now() - timedelta(days=self.not_valid_before_days)

    @property
    def not_valid_after_date(self):
        return datetime.now() + timedelta(days=self.not_valid_after_days)

    def issue_certificate(self, ca_pem_key, ca_pem_cert, csr_pem):

        ca_cert = self.load_pem(entity_type="certificate", pem_text=ca_pem_cert)
        ca_key = self.load_pem(entity_type="key", pem_text=ca_pem_key)
        csr = self.load_pem(entity_type="csr", pem_text=csr_pem)

        builder = x509.CertificateBuilder(
            issuer_name=ca_cert.issuer,
            subject_name=csr.subject,
            public_key=csr.public_key(),
            not_valid_before=self.not_valid_before_date,
            not_valid_after=self.not_valid_after_date,
            extensions=csr.extensions,
            serial_number=self.serial_num,
        )

        certificate = builder.sign(
            private_key=ca_key,
            algorithm=hashes.SHA256(),
            backend=default_backend(),
        )

        self.pem_certificate = certificate.public_bytes(
            encoding=serialization.Encoding.PEM
        )

        return certificate

    def issue_ca(self):
        if not self.private_key:
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size,
                backend=default_backend(),
            )
        else:
            key = self.private_key

        issuer_name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, text_type(self.hostname))]
        )

        serial_number = (
            self.serial_number if self.serial_number else int(uuid.uuid4())
        )

        cert_builder = x509.CertificateBuilder(
            public_key=key.public_key(),
            issuer_name=issuer_name,
            subject_name=self.subject_name,
            serial_number=self.serial_num,
            not_valid_before=self.not_valid_before_date,
            not_valid_after=self.not_valid_after_date,
        )

        cert_builder = cert_builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        )

        certificate = cert_builder.sign(
            private_key=key,
            algorithm=hashes.SHA256(),
            backend=default_backend(),
        )

        self.pem_public_key = key.public_key()

        self.pem_certificate = certificate.public_bytes(
            encoding=serialization.Encoding.PEM
        )

        self.pem_private_key = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return certificate

    def generate_csr(self):
        if not self.private_key:
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size,
                backend=default_backend(),
            )
        else:
            key = self.private_key

        csr_builder = x509.CertificateSigningRequestBuilder(
            subject_name=self.subject_name
        )

        if self.ip_addr_list:
            csr_builder = csr_builder.add_extension(
                self.subject_alt_name, critical=True
            )

        csr = csr_builder.sign(key, hashes.SHA256(), default_backend())
        self.pem_csr = csr.public_bytes(serialization.Encoding.PEM)

        self.pem_private_key = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return csr
