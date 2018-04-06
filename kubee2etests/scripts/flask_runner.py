from flask import Flask
from kubee2etests.frontend.flask_app import healthcheck
import os
from kubee2etests.helpers_and_globals import FLASK_PORT


def main():
    port = int(os.environ.get('FLASK_PORT', FLASK_PORT))
    addr = os.environ.get('FLASK_ADDR', '')
    flask_root = os.path.join(os.getcwd(), "kubee2etests", "frontend")
    app = Flask(__name__, root_path=flask_root)
    app.register_blueprint(healthcheck)
    app.run(port=port, host=addr)


if __name__ == '__main__':
    main()
