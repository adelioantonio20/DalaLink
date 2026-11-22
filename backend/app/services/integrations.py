"""
Phase 4 External Integrations & Partner Adapter Registry.

Strictly obeys DalaLink governance rules:
  - No unauthorized real banking/payment integrations are executed.
  - All external paid or regulated services remain behind clean adapter interfaces
    until contracts, BNA compliance, and budgets are formally approved.
"""

from abc import ABC, abstractmethod


class TicketingIntegrationAdapter(ABC):
    provider_code: str
    display_name: str
    status: str

    @abstractmethod
    def capabilities(self) -> dict:
        raise NotImplementedError


class DalaLinkCoreLedgerAdapter(TicketingIntegrationAdapter):
    provider_code = "DALALINK_CORE_LEDGER"
    display_name = "DalaLink Carteira & Bilhética QR/NFC (Servidor ACID)"
    status = "ACTIVE"

    def capabilities(self) -> dict:
        return {
            "provider_code": self.provider_code,
            "display_name": self.display_name,
            "category": "TICKETING_LEDGER",
            "status": self.status,
            "supports_qr": True,
            "supports_nfc": True,
            "cost_tier": "FREE_INTERNAL",
            "notes": "Ativo em produção piloto. Saldo armazenado apenas no servidor com idempotência e bloqueio em tempo real.",
        }


class AngolaTransitTicketingAdapter(TicketingIntegrationAdapter):
    provider_code = "ANGOLA_PUBLIC_TICKETING_BRIDGE"
    display_name = "Integração Bilhética Urbana de Angola (Ex.: Giro / Passe Social)"
    status = "READY_FOR_PARTNER_AUTH"

    def capabilities(self) -> dict:
        return {
            "provider_code": self.provider_code,
            "display_name": self.display_name,
            "category": "INTEROPERABLE_TICKETING",
            "status": self.status,
            "supports_qr": True,
            "supports_nfc": True,
            "cost_tier": "PARTNER_AGREEMENT",
            "notes": "Interface preparada para interoperabilidade com infraestruturas existentes de bilhética em Angola mediante protocolo técnico.",
        }


class EmisMulticaixaExpressAdapter(TicketingIntegrationAdapter):
    provider_code = "EMIS_MULTICAIXA_EXPRESS"
    display_name = "EMIS / Multicaixa Express (Carregamento Bancário AOA)"
    status = "DISCONNECTED_REQUIRES_APPROVAL"

    def capabilities(self) -> dict:
        return {
            "provider_code": self.provider_code,
            "display_name": self.display_name,
            "category": "PAYMENT_GATEWAY",
            "status": self.status,
            "supports_qr": True,
            "supports_nfc": False,
            "cost_tier": "CONTRACT_AND_FEES",
            "notes": "Desativado por política de segurança. Requer contrato comercial, credenciais EMIS e aprovação financeira explícita.",
        }


class MapAndNotificationInfraAdapter(TicketingIntegrationAdapter):
    provider_code = "LUANDA_MAPS_AND_PUSH"
    display_name = "Mapas OpenStreetMap + WebSockets / Web Push"
    status = "ACTIVE_DEV_PILOT"

    def capabilities(self) -> dict:
        return {
            "provider_code": self.provider_code,
            "display_name": self.display_name,
            "category": "MAPS_AND_MESSAGING",
            "status": self.status,
            "supports_qr": False,
            "supports_nfc": False,
            "cost_tier": "FREE_DEV_PLAN_PROD",
            "notes": "Gratuito no MVP/Piloto. Em escala comercial prever servidor próprio de tiles OSM e gateway SMS aprovado para Angola.",
        }


def list_registered_integrations() -> list[dict]:
    adapters: list[TicketingIntegrationAdapter] = [
        DalaLinkCoreLedgerAdapter(),
        AngolaTransitTicketingAdapter(),
        EmisMulticaixaExpressAdapter(),
        MapAndNotificationInfraAdapter(),
    ]
    return [a.capabilities() for a in adapters]
