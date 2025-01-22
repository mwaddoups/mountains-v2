from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import stripe
from attrs import define

from mountains.errors import MountainException

if TYPE_CHECKING:
    from flask import Flask, Request


class MountainsStripeError(MountainException):
    pass


@define
class EventPaymentMetadata:
    attendee_id: int

    def to_metadata(self) -> dict[str, str]:
        return {"payment_for": "event", "attendee_id": str(self.attendee_id)}

    @classmethod
    def from_metadata(cls, m: dict[str, str]):
        return cls(attendee_id=int(m["attendee_id"]))


@define
class MembershipPaymentMetadata:
    user_id: int
    membership_expiry: datetime.date
    date_of_birth: str
    address: str
    postcode: str
    mobile_number: str
    ms_number: str

    def to_metadata(self) -> dict[str, str]:
        return {
            "payment_for": "membership",
            "user_id": str(self.user_id),
            "membership_expiry": self.membership_expiry.strftime("%Y-%m-%d"),
            "date_of_birth": self.date_of_birth,
            "address": self.address,
            "postcode": self.postcode,
            "mobile_number": self.mobile_number,
            "ms_number": self.ms_number,
        }

    @classmethod
    def from_metadata(cls, m: dict[str, str]):
        return cls(
            user_id=int(m["user_id"]),
            membership_expiry=datetime.datetime.strptime(
                m["membership_expiry"], "%Y-%m-%d"
            ),
            date_of_birth=m["date_of_birth"],
            address=m["address"],
            postcode=m["postcode"],
            mobile_number=m["mobile_number"],
            ms_number=m["ms_number"],
        )


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

    def create_checkout(
        self,
        price_id: str,
        *,
        success_url: str,
        cancel_url: str,
        metadata: MembershipPaymentMetadata | EventPaymentMetadata,
    ) -> str:
        """
        This creates a checkout session for users to pay through.
        """
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                },
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata.to_metadata(),
        )
        if checkout_session.url is None:
            raise MountainsStripeError("Failed to create checkout session!")
        else:
            return checkout_session.url

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

    def event_details(
        self, request: Request
    ) -> tuple[list[stripe.LineItem], dict[str, str] | None]:
        payload = request.get_data()
        sig_header = request.headers["Stripe-Signature"]

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, secret=self.webhook_secret, api_key=self.api_key
            )
        except Exception as e:
            raise MountainsStripeError("Event payload construction failed!") from e

        line_items = []
        metadata = None
        if event["type"] == "checkout.session.completed":
            session = stripe.checkout.Session.retrieve(
                event["data"]["object"]["id"],
                expand=["line_items"],
            )

            if session.line_items is not None:
                line_items = session.line_items.data

            metadata = session.metadata

        return line_items, metadata
