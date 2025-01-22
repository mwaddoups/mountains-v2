import stripe
from attrs import define


@define
class StripeAPI:
    api_key: str
    webhook_secret: str

    def list_prices(self) -> list[stripe.Price]:
        prices = stripe.Price.list(
            active=True, limit=100, expand=["data.product"], api_key=self.api_key
        ).data

        return prices

    def get_price(self, id: str) -> stripe.Price:
        return stripe.Price.retrieve(id=id, expand=["product"])
