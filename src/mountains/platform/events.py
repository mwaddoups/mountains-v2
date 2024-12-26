import datetime

from quart import Blueprint, current_app, render_template, request

from mountains.errors import MountainException

from ..events import Event, events


def events_repo():
    return events(current_app.config["DB_NAME"])


def event_routes(blueprint: Blueprint):
    @blueprint.route("/events", methods=["GET", "POST"])
    async def events():
        if request.method == "POST":
            form_data = await request.form

            event = Event.from_new_event(
                title=form_data["title"],
                description=form_data["description"],
                event_dt_str=form_data["event_dt"],
                event_end_dt_str=form_data["event_end_dt"],
                event_type_str=form_data["event_type"],
                max_attendees_str=form_data["max_attendees"],
            )
            events_repo().insert(event)

            # TODO: Audit the event

        # TODO: reasonable day threshold, old and new events
        events = sorted(
            [
                e
                for e in events_repo().list()
                if e.event_dt > datetime.datetime.now() - datetime.timedelta(days=2)
            ],
            key=lambda e: e.event_dt,
        )
        return await render_template("platform/events.html.j2", events=events)

    @blueprint.route("/events/add")
    @blueprint.route("/events/edit/<id>")
    async def edit_event(id: str | None = None):
        if id is not None:
            event = events_repo().get(id=id)
            if event is None:
                raise MountainException("Event not found!")
        else:
            event = None
        return await render_template(
            "platform/event.edit.html.j2", event=event, event_types=Event.event_types()
        )
