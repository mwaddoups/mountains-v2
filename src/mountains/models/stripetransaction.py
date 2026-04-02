import datetime
import sqlite3

from attrs import define

from mountains.db import Repository


@define
class StripeTransaction:
    """
    A balance transaction from Stripe, linked up with our internal IDs

    All amounts in pennies

    :param id: corresponds exactly to balance ID in stripe
    """

    id: str
    dt_utc: datetime.datetime
    stripe_type: str
    gross_p: int
    stripe_fee_p: int
    net_p: int
    payment_type: str | None = None
    user_id: int | None = None
    event_id: int | None = None

    def net(self) -> float:
        return self.net_p / 100

    def gross(self) -> float:
        return self.gross_p / 100

    def stripe_fee(self) -> float:
        return self.stripe_fee_p / 100

    def category(self) -> str:
        """
        Attempts to categorize these based on our understanding
        """
        match self.stripe_type:
            case "payout":
                return "Payout"
            case "payment" | "charge":
                if self.payment_type == "membership":
                    return "Membership"
                else:
                    return "Event"
            case "refund" | "payment_refund":
                return "Refund"
            case "stripe_fee":
                # Some kind of stripe fee that we probably don't want to be paying!!
                return "Stripe Fee"
            case "adjustment":
                # We almost never get these, but got £5 once
                # Usually to do with some technical detail and should likely be accounted for as bank charges
                return "Stripe Fee"
            case "advance" | "advance_funding":
                # We may have requested an instant payout once and been charged this
                return "Stripe Fee"
            case _:
                return "Unknown"


def stripe_transactions_repo(conn: sqlite3.Connection) -> Repository[StripeTransaction]:
    return Repository(
        conn=conn,
        table_name="stripe_transactions",
        schema=[
            "id TEXT PRIMARY KEY",
            "dt_utc DATETIME NOT NULL",
            "stripe_type TEXT NOT NULL",
            "gross_p INTEGER NOT NULL",
            "stripe_fee_p INTEGER NOT NULL",
            "net_p INTEGER NOT NULL",
            "payment_type TEXT",
            "user_id INTEGER",
            "event_id INTEGER",
            "FOREIGN KEY(user_id) REFERENCES users(id)",
            "FOREIGN KEY(event_id) REFERENCES events(id)",
        ],
        storage_cls=StripeTransaction,
    )
