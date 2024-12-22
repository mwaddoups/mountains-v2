from quart import Quart, render_template

from . import platform


def create_app():
    app = Quart(__name__)

    app.register_blueprint(platform.blueprint)

    @app.route("/")
    async def index():
        return await render_template("index.html.j2")

    return app
