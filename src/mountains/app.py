from quart import Quart, render_template


def create_app():
    app = Quart(__name__)

    @app.route("/")
    async def index():
        return await render_template("index.html.j2")

    return app
