import logging

import mistune
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


def send_mail(
    *, to: list[str], subject: str, msg_markdown: str, api_key: str, debug: bool = True
) -> None:
    if debug:
        print("DEBUG EMAIL", subject, msg_markdown)
        return
    else:
        api_url = "https://api.eu.mailgun.net/v3/mg.clydemc.org/messages"

        data = [
            ("from", "Clyde Mountaineering Club <noreply@clydemc.org>"),
            ("subject", subject),
            ("text", msg_markdown),
            ("html", mistune.html(msg_markdown)),
        ] + [("to", to_email) for to_email in to]

        res = requests.post(api_url, auth=HTTPBasicAuth("api", api_key), data=data)
        if res.status_code != 200:
            logger.error("Error in sending email! Data: %r, response: %r", data, res)
        else:
            logger.info("Sending email with subject %s to %r", subject, to)
