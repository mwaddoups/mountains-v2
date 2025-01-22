from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import stripe
from attrs import define

from mountains.errors import MountainException

if TYPE_CHECKING:
    from flask import Flask


class MountainsStripeError(MountainException):
    pass


@define
class StripeAPI:
    api_key: str
    webhook_secret: str

    @classmethod
    def from_app(cls, app: Flask):
        return cls(
            api_key=app.config["STRIPE_API_KEY"],
            webhook_secret=app.config["STRIPE_WEBHOOK_SECRET"],
        )

    def membership_options(self, target_expiry: datetime.date) -> list[stripe.Price]:
        """
        Gets the latest available membership from Stripe, together with the list of
        active prices.

        This relies on
        - treasurer setting 'membership' = 'true' in the membership product metadata
        - treasurer setting 'membership_expiry' = YYYY-MM-DD in the product metadata
        """

        # Get all membership products for that expiry
        expiry_str = target_expiry.strftime("%Y-%m-%d")
        membership_products = stripe.Product.search(
            query=f"active:'true' AND metadata['membership']:'true' AND metadata['membership_expiry']:'{expiry_str}'",
            limit=100,
            api_key=self.api_key,
        ).data

        if len(membership_products) == 0:
            raise MountainsStripeError(
                f"No active membership products found for expiry {target_expiry}!"
            )

        # Get all prices for these product
        prices = []
        for p in membership_products:
            prices += stripe.Price.list(
                active=True,
                limit=100,
                currency="gbp",
                product=p["id"],
                api_key=self.api_key,
                expand=["data.product"],
            ).data

        # Sort descending so we get full price first
        return sorted(prices, key=lambda p: p.unit_amount, reverse=True)
