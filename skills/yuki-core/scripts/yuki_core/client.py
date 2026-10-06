"""Read-only Yuki SOAP client. Every call passes one allowlist; Yuki writes are impossible by design.

Yuki API keys carry write rights (keys are scoped per administration, not read vs write),
so the allowlist below is the only safety net. Extend it deliberately, never with a write method.
"""

from __future__ import annotations

import logging

from zeep import Client
from zeep.transports import Transport

# Generic host: tenant hosts (l3038-<name>.yukiworks.be) reject calls with
# "Webservice calls have to be made on a valid domain". NL tenants use api.yukiworks.nl.
BASE_URL = "https://api.yukiworks.be/ws"
TIMEOUT = 120  # seconds, for WSDL loads and operations alike
ALLOWED = {
    ("AccountingInfo", "Authenticate"),
    ("AccountingInfo", "SetCurrentDomain"),
    ("AccountingInfo", "Domains"),          # discovery
    ("AccountingInfo", "Administrations"),  # discovery
    ("Accounting", "OutstandingCreditorItems"),
}

logging.getLogger("zeep").setLevel(logging.ERROR)  # silences "Forcing soap:address location to HTTPS"


class YukiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session_id: str | None = None
        self._services: dict[str, Client] = {}

    def call(self, service: str, method: str, **params):
        """SOAP parameter names are case-sensitive: `sessionID`, `administrationID` (a wrong
        casing yields a misleading "Invalid session ID")."""
        if (service, method) not in ALLOWED:
            raise PermissionError(f"Yuki {service}.{method} is not on the read-only allowlist")
        if service not in self._services:
            transport = Transport(timeout=TIMEOUT, operation_timeout=TIMEOUT)
            self._services[service] = Client(f"{BASE_URL}/{service}.asmx?WSDL", transport=transport)
        return getattr(self._services[service].service, method)(**params)

    def connect(self, domain_id: str) -> "YukiClient":
        self.session_id = self.call("AccountingInfo", "Authenticate", accessKey=self.api_key)
        if not self.session_id:
            raise RuntimeError("Yuki authentication failed: no session ID returned")
        self.call("AccountingInfo", "SetCurrentDomain", sessionID=self.session_id, domainID=domain_id)
        return self

    def domains(self):
        return self.call("AccountingInfo", "Domains", sessionID=self.session_id)

    def administrations(self):
        """Administrations of the current domain (set by connect)."""
        return self.call("AccountingInfo", "Administrations", sessionID=self.session_id)

    def outstanding_creditor_items(self, administration_id: str):
        """"Aan te leveren aankoopfacturen": includeBankTransactions=True adds the unmatched
        bank/card payments; without it only booked invoices come back."""
        return self.call("Accounting", "OutstandingCreditorItems", sessionID=self.session_id,
                         administrationID=administration_id, includeBankTransactions=True,
                         sortOrder="DateAsc")
