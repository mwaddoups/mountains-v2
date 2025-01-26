import datetime
import logging
import textwrap

import mistune
from flask import Flask, Response, current_app, g, render_template, request, session
from flask.logging import default_handler

from mountains.context import db_conn, send_mail
from mountains.discord import DiscordAPI
from mountains.payments import (
    EventPaymentMetadata,
    MembershipPaymentMetadata,
    StripeAPI,
)

from . import auth, platform
from .models.events import attendees_repo, events_repo
from .models.pages import latest_content
from .models.photos import photos_repo
from .models.tokens import tokens_repo
from .models.users import users_repo


def create_app():
    app = Flask(__name__)

    # Set up logging for any logger on 'mountains'
    logger = logging.getLogger("mountains")
    logger.setLevel(logging.INFO)
    logger.addHandler(default_handler)

    # Load from the local .env file
    app.config.from_prefixed_env("FLASK")
    logger.info("Running on DB: %s", app.config["DB_NAME"])
    # Ensure the session cookie as secure
    app.jinja_options["autoescape"] = True
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    app.config.update(
        CMC_MEMBERSHIP_EXPIRY=datetime.date(2025, 3, 31),
        CMC_MAX_TRIAL_EVENTS=4,
    )

    app.register_blueprint(platform.blueprint)
    app.register_blueprint(auth.blueprint)

    @app.template_filter("markdown")
    def convert_markdown(s: str) -> str:
        return mistune.html(s)  # type: ignore

    @app.context_processor
    def now_dt() -> dict:
        return {"now": datetime.datetime.now()}

    @app.route("/")
    def index():
        with db_conn() as conn:
            page = latest_content(conn, "front-page")
            upcoming_events = [e for e in events_repo(conn).list() if e.is_upcoming()]
            upcoming_events = sorted(upcoming_events, key=lambda e: e.event_dt)[:6]

            recent_photos = [p for p in photos_repo(conn).list_where(starred=True)]
            recent_photos = sorted(
                recent_photos, key=lambda p: p.created_at_utc, reverse=True
            )[:24]

        return render_template(
            "landing.html.j2",
            page=page,
            upcoming_events=upcoming_events,
            recent_photos=recent_photos,
        )

    @app.route("/faqs")
    def faqs():
        with db_conn() as conn:
            page = latest_content(conn, "faqs")
        return render_template("page.html.j2", page=page)

    @app.route("/committee")
    def committee_bios():
        with db_conn() as conn:
            committee = [u for u in users_repo(conn).list_where(is_committee=True)]
        return render_template("committee.bios.html.j2", committee=committee)

    @app.route("/privacy-policy")
    def privacy_policy():
        with db_conn() as conn:
            page = latest_content(conn, "privacy-policy")
        return render_template("page.html.j2", page=page)

    # This route is fixed and set in Stripe config
    @app.post("/api/payments/handleorder")
    def handle_stripe_order():
        """
        This is a webhook that is called by stripe to process orders.

        It should always respond 200 OK to indicate receipt.

        To test this in testing mode, run
        ./stripe listen --forward-to localhost:5000/api/payments/handleorder

        On a normal order, we receive
        - payment_intent.created
        - payment_intent.succeeded
        - charge.updated
        - charge.succeeded
        - checkout.session.completed

        We only handle checkout.session.completed and use the metadata we passed earlier.
        """
        stripe_api = StripeAPI.from_app(current_app)

        event = stripe_api.to_event(request)
        if event.type != "checkout.session.completed":
            logger.info("Ignoring event with type: %s", event.type)
            return Response(status=200)

        line_items, metadata = stripe_api.checkout_items_metadata(event)

        # Handle some cases we don't expect here
        # TODO: Email about these
        if metadata is None:
            logger.error("Received line items %r without metadata!", line_items)
            return Response(status=200)
        elif len(line_items) != 1:
            logger.error(
                "Received an attempt to pay for more than one item! Items: %r, metadata: %r",
                line_items,
                metadata,
            )
            return Response(status=200)

        with db_conn() as conn:
            if metadata.get("payment_for") == "event":
                # It's an event, lets set them as paid
                event_payment = EventPaymentMetadata.from_metadata(metadata)
                attendees_repo(conn).update(
                    _where=dict(
                        user_id=event_payment.user_id, event_id=event_payment.event_id
                    ),
                    is_trip_paid=True,
                )
            elif metadata.get("payment_for") == "membership":
                # It's a membership payment, lets set member and email the treasurer
                payment = MembershipPaymentMetadata.from_metadata(metadata)
                user_db = users_repo(conn)

                user = user_db.get_or_404(id=payment.user_id)
                user_db.update(
                    id=user.id,
                    membership_expiry=payment.membership_expiry,
                )

                if user.membership_expiry is None and user.discord_id is not None:
                    # They were previously not a member, lets set it on Discord.
                    DiscordAPI.from_app(current_app).set_member_role(user.discord_id)

                # And send the emails
                send_mail(
                    to=[user.email],
                    subject="Thank you for joining!",
                    msg_markdown="\n\n".join([
                        "# Thank you for joining!",
                        "Your membership on the website should now be confirmed.",
                        "Your membership should shortly be set up on Discord, and the treasurer will register you for Mountaineering Scotland as soon as they are able. \n\n"
                        "If you have any issues, message on Discord or contact treasurer@clydemc.org ."
                        "Thank you!",
                    ]),
                )
                send_mail(
                    to=["treasurer@clydemc.org"],
                    subject=f"New paid member - {user.full_name}!",
                    msg_markdown=textwrap.dedent(f"""
                        # {user.full_name} has joined the club!

                        See their details below (for adding to MS):
                        - Full Name: {user.full_name}
                        - Email: {user.email}
                        - Date of Birth: {payment.date_of_birth}
                        - Address: {payment.address}
                        - Postcode: {payment.postcode}
                        - Mobile: {payment.mobile_number}
                        - MS Number: {payment.ms_number if payment.ms_number else "<None provided>"}
                        """),
                )
            else:
                # Send error email!
                send_mail(
                    to=["treasurer@clydemc.org", "admin@clydemc.org"],
                    subject="Unknown payment!",
                    msg_markdown=textwrap.dedent(f"""
                        # Unknown payment from Stripe!

                        We received an unknown payment that we could not map to an existing event or membership. 
                        
                        Check Stripe for more details - see raw details below:

                        ## Line Items

                        ```
                        {line_items:!r}
                        ```

                        ## Metadata

                        ```
                        {metadata:!r}
                        ```
                        """),
                )

        return Response(status=200)

    @app.before_request
    def current_user():
        # Ensure all requests have access to the current user, if logged in
        if (token_id := session.get("token_id")) is not None:
            with db_conn() as conn:
                token = tokens_repo(conn).get(id=token_id)
                if (
                    token is not None
                    and (user := users_repo(conn).get(id=token.user_id)) is not None
                ):
                    g.current_user = user

    return app
