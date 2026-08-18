from dataclasses import dataclass
from typing import Optional
from enum import Enum

from ..config import settings


class LicenseStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


@dataclass
class LicenseResult:
    status: LicenseStatus
    license_type: str
    attribution_required: bool = False
    attribution_text: Optional[str] = None
    proof_url: Optional[str] = None
    reason: Optional[str] = None


LICENSE_ATTRIBUTIONS = {
    "cc_by_4.0": "This work is licensed under a Creative Commons Attribution 4.0 International License (CC BY 4.0).",
    "cc_by_sa_4.0": "This work is licensed under a Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0).",
    "cc0_1.0": "This work is dedicated to the public domain via CC0 1.0 Universal.",
}


class LicenseVerifier:
    """Verifies whether a book's license permits commercial resale."""

    def verify(self, license_type: Optional[str], license_url: Optional[str] = None) -> LicenseResult:
        if not license_type:
            return LicenseResult(
                status=LicenseStatus.PENDING,
                license_type="unknown",
                reason="No license information provided",
            )

        normalized = self._normalize(license_type)

        if self._is_blocked(normalized):
            return LicenseResult(
                status=LicenseStatus.REJECTED,
                license_type=normalized,
                reason=f"License '{normalized}' is not eligible for commercial resale",
            )

        if self._is_approved(normalized):
            return LicenseResult(
                status=LicenseStatus.APPROVED,
                license_type=normalized,
                attribution_required=normalized.startswith("cc_by"),
                attribution_text=LICENSE_ATTRIBUTIONS.get(normalized),
                proof_url=license_url,
            )

        return LicenseResult(
            status=LicenseStatus.PENDING,
            license_type=normalized,
            reason=f"Unrecognized license: {normalized} — requires manual review",
        )

    def _normalize(self, license_type: str) -> str:
        lt = license_type.lower().strip().replace("-", "_").replace(" ", "_")
        lt = lt.replace("creative_commons_", "cc_")
        if "publicdomain" in lt or lt == "pd" or "public_domain" in lt:
            return "public_domain"
        if lt in ("cc0", "cc0_1.0"):
            return "cc0_1.0"
        if "by_nc" in lt:
            return "cc_by_nc"
        if "by_nd" in lt:
            return "cc_by_nd"
        if "by_sa" in lt:
            return "cc_by_sa_4.0"
        if "by" in lt and "_nc" not in lt and "_nd" not in lt:
            return "cc_by_4.0"
        return lt

    def _is_approved(self, license_type: str) -> bool:
        return license_type in settings.ALLOWED_LICENSES

    def _is_blocked(self, license_type: str) -> bool:
        return any(blocked in license_type for blocked in settings.BLOCKED_LICENSES)


license_verifier = LicenseVerifier()