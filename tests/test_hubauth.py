"""The deployment inside Market Hub admits only people signed in there; earningsradar.app stays public."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from test_ondemand import MemoryStore, _analyser, directory, edgar_stub  # noqa: F401 (fixtures)

from decisionsignal.api import create_app
from decisionsignal.config import ONDEMAND_PER_IP_PER_HOUR
from decisionsignal.hubauth import read_user

SECRET = "hub-secret"
HUB = "https://themarkethub.app"
USER = {"id": "1001", "email": "ana@gmail.com", "name": "Ana", "picture": ""}


def hub_cookie(secret: str = SECRET) -> str:
    """A session cookie made exactly as the hub makes it (Starlette's SessionMiddleware)."""
    def login(request):
        request.session["user"] = USER
        return PlainTextResponse("ok")

    hub = Starlette(routes=[Route("/", login)],
                    middleware=[Middleware(SessionMiddleware, secret_key=secret, session_cookie="mh_session")])
    return TestClient(hub).get("/").cookies["mh_session"]


def site(tmp_path):
    root = tmp_path / "site"
    (root / "analyze").mkdir(parents=True)
    (root / "index.html").write_text("<h1>home</h1>")
    (root / "analyze" / "index.html").write_text("<h1>analyze</h1>")
    return str(root)


def test_read_user_rejects_forged_cookies():
    assert read_user(hub_cookie(), SECRET) == USER
    assert read_user(hub_cookie("forged"), SECRET) is None


def test_inside_the_hub_only_signed_in_users_get_in(tmp_path, edgar_stub, directory):
    app = create_app(analyser=_analyser(tmp_path, MemoryStore(), []), directory=directory, static_dir=site(tmp_path),
                     hub=(HUB, SECRET))
    c = TestClient(app, base_url="https://radar.themarkethub.app", follow_redirects=False)
    assert c.get("/api/health").status_code == 200
    page = c.get("/analyze/", params={"ticker": "ZETA"})
    target = urlparse(page.headers["location"])
    assert page.status_code == 302 and f"{target.scheme}://{target.netloc}{target.path}" == f"{HUB}/signin/"
    assert parse_qs(target.query)["next"] == ["https://radar.themarkethub.app/analyze/?ticker=ZETA"]
    assert c.get("/api/analysis/zeta").status_code == 401

    c.cookies.set("mh_session", hub_cookie())
    assert c.get("/api/me").json() == {"user": USER, "hub": HUB}
    assert "analyze" in c.get("/analyze/").text
    # No per-address limit behind the sign-in (stored analyses cost nothing).
    for _ in range(ONDEMAND_PER_IP_PER_HOUR + 3):
        assert c.get("/api/analysis/zeta").status_code == 200


def test_the_public_deployment_is_unchanged(tmp_path, edgar_stub, directory):
    app = create_app(analyser=_analyser(tmp_path, MemoryStore(), []), directory=directory, static_dir=site(tmp_path), hub=None)
    c = TestClient(app)
    assert c.get("/api/me").json() == {"user": None, "hub": None}
    assert "home" in c.get("/").text
    codes = [c.get("/api/analysis/zeta").status_code for _ in range(ONDEMAND_PER_IP_PER_HOUR + 1)]
    assert codes[-1] == 429
