from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Literal

import stripe
from attrs import define

from mountains.errors import MountainException
from mountains.models.stripetransaction import StripeTransaction

if TYPE_CHECKING:
    from flask import Flask, Request

logger = logging.getLogger(__name__)


class MountainsStripeError(MountainException):
    pass


@define
class EventPaymentMetadata:
    user_id: int
    event_id: int

    def to_metadata(self) -> dict[str, str]:
        return {
            "payment_for": "event",
            "user_id": str(self.user_id),
            "event_id": str(self.event_id),
        }

    @classmethod
    def from_metadata(cls, m: dict[str, str]):
        return cls(user_id=int(m["user_id"]), event_id=int(m["event_id"]))


@define
class MembershipPaymentMetadata:
    user_id: int
    membership_expiry: datetime.date
    date_of_birth: str
    address: str
    postcode: str
    mobile_number: str
    ms_number: str

    def validate(self, are_existing: Literal["yes", "no"]) -> None:
        """
        Raises a MountainException on any incorrect fields

        :param are_existing: should be either 'yes' or 'no'
        """
        now = datetime.date.today()
        try:
            dob = datetime.date.fromisoformat(self.date_of_birth)
        except Exception:
            raise MountainException("Date of birth not valid!")
        if (now - dob).days < 17 * 365:
            raise MountainException(
                f"Date of birth {self.date_of_birth} would make you younger than 18 - the club is only open to over 18s."
            )
        if len(self.address) < 8:
            raise MountainException("Address looks too short.")
        if are_existing == "yes" and len(self.ms_number) < 3:
            raise MountainException(
                "Please provide your existing MS number if you are already a member."
            )

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
            ).date(),
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
            api_key=self.api_key,
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

    def to_event(self, request: Request) -> stripe.Event:
        payload = request.get_data()
        sig_header = request.headers["Stripe-Signature"]

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, secret=self.webhook_secret, api_key=self.api_key
            )
        except Exception as e:
            raise MountainsStripeError("Event payload construction failed!") from e
        return event

    def checkout_items_metadata(
        self, event: stripe.Event
    ) -> tuple[list[stripe.LineItem], dict[str, str] | None]:
        line_items = []
        metadata = None
        if event["type"] == "checkout.session.completed":
            session = stripe.checkout.Session.retrieve(
                event["data"]["object"]["id"],
                expand=["line_items"],
                api_key=self.api_key,
            )

            if session.line_items is not None:
                line_items = session.line_items.data

            metadata = session.metadata

        return line_items, metadata

    def fetch_balance_transactions(
        self,
        since: StripeTransaction | None = None,
        before: StripeTransaction | None = None,
    ) -> list[StripeTransaction]:
        """
        Fetches all balance transactions from stripe, linking these with ids and members.

        :param since: if passed, find all transactions after this transaction
        """
        if since:
            balances = stripe.BalanceTransaction.list(
                api_key=self.api_key,
                ending_before=since.id,
                expand=["data.source"],
                limit=100,
            )
        elif before:
            balances = stripe.BalanceTransaction.list(
                api_key=self.api_key,
                starting_after=before.id,
                expand=["data.source"],
                limit=100,
            )
        else:
            balances = stripe.BalanceTransaction.list(
                api_key=self.api_key,
                expand=["data.source"],
                limit=100,
            )

        trans: list[StripeTransaction] = []

        for b in balances:
            dt = datetime.datetime.fromtimestamp(b.created)
            amount = b.amount
            fee = b.fee
            net = b.net
            trans_type = b.type
            match b.type:
                case "payment" | "charge":
                    try:
                        # Payments either for events or membership, can be accounted for via metadata
                        payment_intent_id = b.source.payment_intent  # type: ignore
                        checkout_sessions = stripe.checkout.Session.list(
                            payment_intent=payment_intent_id,  # type: ignore
                            api_key=self.api_key,  # type: ignore
                        )
                        # There is always exactly one checkout session unless we start using subscriptions
                        checkout_session = checkout_sessions.data[0]
                        metadata = checkout_session.metadata
                        assert metadata is not None

                        if metadata["payment_for"] == "membership":
                            trans.append(
                                StripeTransaction(
                                    id=b.id,
                                    dt_utc=dt,
                                    gross_p=amount,
                                    stripe_fee_p=fee,
                                    net_p=net,
                                    stripe_type=trans_type,
                                    payment_type="membership",
                                    user_id=int(metadata["user_id"]),
                                )
                            )
                        elif metadata["payment_for"] == "event":
                            trans.append(
                                StripeTransaction(
                                    id=b.id,
                                    dt_utc=dt,
                                    gross_p=amount,
                                    stripe_fee_p=fee,
                                    net_p=net,
                                    stripe_type=trans_type,
                                    payment_type="event",
                                    user_id=int(metadata["user_id"]),
                                    event_id=int(metadata["event_id"]),
                                )
                            )
                        else:
                            raise MountainException(f"Unknown metadata: {metadata}")
                    except Exception as e:
                        logger.error("Error handling transaction", exc_info=e)
                        trans.append(
                            StripeTransaction(
                                id=b.id,
                                dt_utc=dt,
                                gross_p=amount,
                                stripe_fee_p=fee,
                                net_p=net,
                                stripe_type=trans_type,
                                payment_type="unknown",
                            )
                        )
                case "refund" | "payment_refund":
                    try:
                        # Link this back to the checkout session for the refund
                        refund_charge = b.source.charge  # type: ignore
                        charge = stripe.Charge.retrieve(
                            api_key=self.api_key,
                            id=refund_charge,  # type: ignore
                        )
                        payment_intent_id = charge.payment_intent
                        checkout_sessions = stripe.checkout.Session.list(
                            payment_intent=charge.payment_intent,  # type: ignore
                            api_key=self.api_key,  # type: ignore
                        )
                        # There is always exactly one checkout session unless we start using subscriptions
                        checkout_session = checkout_sessions.data[0]
                        metadata = checkout_session.metadata
                        assert metadata is not None
                        trans.append(
                            StripeTransaction(
                                id=b.id,
                                dt_utc=dt,
                                gross_p=amount,
                                stripe_fee_p=fee,
                                net_p=net,
                                stripe_type=trans_type,
                                payment_type="refund",
                                event_id=int(metadata["event_id"])
                                if "event_id" in metadata
                                else None,
                                user_id=int(metadata["user_id"])
                                if "user_id" in metadata
                                else None,
                            )
                        )
                    except Exception:
                        trans.append(
                            StripeTransaction(
                                id=b.id,
                                dt_utc=dt,
                                gross_p=amount,
                                stripe_fee_p=fee,
                                net_p=net,
                                stripe_type=trans_type,
                                payment_type="unknown refund",
                            )
                        )
                case _:
                    trans.append(
                        StripeTransaction(
                            id=b.id,
                            dt_utc=dt,
                            gross_p=amount,
                            stripe_fee_p=fee,
                            net_p=net,
                            stripe_type=trans_type,
                        )
                    )

        return trans
