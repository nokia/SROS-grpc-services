############################################################################
#
#   Filename:           gnoi_cert.py
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

import grpc_lib

from protos_gen import cert_pb2 as cert
from protos_gen import cert_pb2_grpc as cert_stub

from logging import getLogger
import base64

logger = getLogger(__name__)


def create_stub(service=None, channel=None):
    return cert_stub.CertificateManagementStub(channel)


class CanGenerateCSR(grpc_lib.Rpc):
    def __init__(self, key_type, certificate_type, key_size, *args, **kwargs):

        grpc_lib.Rpc.__init__(self, *args, **kwargs)

        self.processed_request = []
        self.stub_method = self.stub.CanGenerateCSR

        self.response_processor = self.default_response_processor
        self.request_type = "unary"

        self.key_type = key_type
        self.certificate_type = certificate_type
        self.key_size = key_size

        self.response = None

    def __str__(self):
        return (
            "REQUEST:\n{request}\n\n"
            "RESPONSE:\n{response}\n\n"
            "ERROR:\n{error}\n"
        ).format(request=self.request, response=self.response, error=self.error)

    def generator(self):
        return self.request

    @property
    def request(self):
        return cert.CanGenerateCSRRequest(
            key_type=self.key_type,
            certificate_type=self.certificate_type,
            key_size=self.key_size,
        )

    def receiver(self):
        self.rpc_handler = self.stub_method.future(
            self.generator(), metadata=self.metadata, timeout=self._timeout
        )
        self.response_processor(self.rpc_handler.result())
        self.status = "finished"
        self.work_queue.task_done()

    def default_response_processor(self, response=None):
        self.response = response


class CertRpc(grpc_lib.Rpc):
    def __init__(
        self,
        certificate_id=None,
        timeout=60,
        certificate=None,
        rpc=None,
        *args,
        **kwargs
    ):
        grpc_lib.Rpc.__init__(self, *args, **kwargs)
        self.certificate_id = certificate_id
        self.requests = []
        self.response = None
        self.response_processor = self.default_response_processor
        self.certificate = certificate
        self.timeout = timeout
        self.request_type = "streaming"
        self.rpc_type = rpc
        if rpc == "install":
            self.stub_method = self.stub.Install
            self.base_method = cert.InstallCertificateRequest
        elif rpc == "rotate":
            self.stub_method = self.stub.Rotate
            self.base_method = cert.RotateCertificateRequest

    def __str__(self):
        display = "CertRpc - {}\n".format(self.rpc_type)
        display += "    id: {}\n".format(self.certificate_id)
        return display

    def generator(self):
        while True:
            self.work_queue.get()
            self.status = "processing"
            for req in self.requests:
                yield req
            self.requests = []

    def receiver(self):
        self.rpc_handler = self.stub_method(
            self.generator(), metadata=self.metadata, timeout=self._timeout
        )
        for msg in self.rpc_handler:
            self.response_processor(msg)
            self.status = "waiting"
            self.work_queue.task_done()

    def default_response_processor(self, response=None):
        self.response = response

    def add_request(self, request):
        self.requests.append(request)

    def generate_csr_request(self):
        return self.base_method(
            generate_csr=cert.GenerateCSRRequest(
                certificate_id=self.certificate_id,
                csr_params=cert.CSRParams(
                    type="CT_X509",
                    min_key_size=self.certificate.key_size,
                    key_type="KT_RSA",
                    common_name=self.certificate.common_name,
                    country=self.certificate.country,
                    state=self.certificate.state,
                    city=self.certificate.city,
                    organization=self.certificate.organization,
                    organizational_unit=self.certificate.organizational_unit,
                    ip_address=",".join(self.certificate.ip_addr_list),
                    email_id=self.certificate.email_id,
                ),
            )
        )

    def load_certificate_request(self, local_keys=False):
        if local_keys:
            key_pair = cert.KeyPair(
                private_key=self.certificate.pem_private_key,
                public_key=self.certificate.pem_csr,
            )
        else:
            key_pair = None

        return self.base_method(
            load_certificate=cert.LoadCertificateRequest(
                certificate_id=self.certificate_id,
                certificate=cert.Certificate(
                    type="CT_X509",
                    certificate=self.certificate.pem_certificate,
                ),
                key_pair=key_pair,
            )
        )

    def finalize_request(self):
        return self.base_method(finalize_rotation=cert.FinalizeRequest())

    def generate_csr(self):
        self.requests.append(self.generate_csr_request())
        self.execute(timeout=self.timeout)
        self.wait(timeout=self.timeout)
        if self.error:
            raise RuntimeError(
                "Rpc failed failed with error: {}".format(self.error)
            )
        if self.response:
            self.certificate.pem_csr = self.response.generated_csr.csr.csr
            self.response = None
        else:
            raise RuntimeError(
                "No response received from router after {}s".format(
                    self.timeout
                )
            )

    def load_certificate(self, local_keys=False):
        self.requests.append(
            self.load_certificate_request(local_keys=local_keys)
        )
        self.execute(timeout=self.timeout)
        self.wait(timeout=self.timeout)
        if self.error:
            raise RuntimeError(
                "Rpc failed failed with error: {}".format(self.error)
            )
        if not self.response:
            raise RuntimeError(
                "No response received from router after {}s".format(
                    self.timeout
                )
            )
        self.response = None

    def finalize(self):
        self.requests.append(self.finalize_request())
        self.execute(timeout=self.timeout)
        self.wait(timeout=self.timeout)
        self.response = None
